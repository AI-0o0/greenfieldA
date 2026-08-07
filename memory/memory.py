import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    BaseMessage,
)
from memory.promote_or_drop import MemoryRoutingDecision, decide_memory_fate


class LongTermMemory:
    """Stores long-term facts and episodic events in a local JSON file."""
    def __init__(self, storage_path: str = "long_term_memory.json"):
        self.storage_path = storage_path
        self.semantic_facts: Dict[str, str] = {}
        self.episodic_events: List[Dict[str, Any]] = []
        self._load_from_file()

    def _load_from_file(self):
        """Loads memory state from the JSON file if it exists."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.semantic_facts = data.get("semantic_facts", {})
                    self.episodic_events = data.get("episodic_events", [])
            except Exception as e:
                print(f"[Memory Load Warning]: Could not read storage file: {e}")

    def _save_to_file(self):
        """Saves current memory state back to the JSON file."""
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump({
                    "semantic_facts": self.semantic_facts,
                    "episodic_events": self.episodic_events,
                }, f, indent=2)
        except Exception as e:
            print(f"[Memory Save Warning]: Could not save to storage file: {e}")

    def add_fact(self, key: str, fact: str):
        self.semantic_facts[key] = fact
        self._save_to_file()

    def add_event(self, summary: Optional[str], context: Optional[str], outcome: Optional[str]):
        self.episodic_events.append({
            "summary": summary,
            "context": context,
            "outcome": outcome,
        })
        self._save_to_file()


class ShortTermMemory:
    """Manages active conversation context and routes evicted items to long-term memory."""
    def __init__(self, max_turns: int = 20, long_term_memory: Optional[LongTermMemory] = None):
        self.max_turns = max_turns
        self.messages: List[BaseMessage] = []
        self.scratchpad: Dict[str, Any] = {}
        self.long_term = long_term_memory or LongTermMemory()

    def set_system_prompt(self, content: str):
        """Maintains a single active system prompt at index 0."""
        if self.messages and isinstance(self.messages[0], SystemMessage):
            self.messages[0] = SystemMessage(content=content)
        else:
            self.messages.insert(0, SystemMessage(content=content))

    def add_user(self, content: str):
        self.messages.append(HumanMessage(content=content))
        self._truncate()

    def add_ai(self, content: str):
        self.messages.append(AIMessage(content=content))
        self._truncate()

    def add_observation(self, content: str):
        self.messages.append(HumanMessage(content=f"[Observation]: {content}"))
        self._truncate()

    def _route_evicted_message(self, msg: BaseMessage):
        """Evaluates evicted messages and routes them to long-term memory stores."""
        item_text = f"{msg.type}: {msg.content}"
        
        try:
            decision: MemoryRoutingDecision = decide_memory_fate(item_text)
            
            if decision.destination == "semantic" and decision.fact:
                key = decision.fact_key or f"fact_{len(self.long_term.semantic_facts) + 1}"
                self.long_term.add_fact(key, decision.fact)
                
            elif decision.destination == "episodic" and (decision.event_summary or decision.context):
                self.long_term.add_event(
                    summary=decision.event_summary,
                    context=decision.context,
                    outcome=decision.outcome,
                )
        except Exception as e:
            # Prevent routing failures from crashing the main agent execution loop
            print(f"[Memory Routing Warning]: Failed to route message: {e}")
    def _truncate(self):
        """Preserves the root SystemMessage while evicting older conversational turns."""
        has_system = len(self.messages) > 0 and isinstance(self.messages[0], SystemMessage)
        system_msg = [self.messages[0]] if has_system else []
        history = self.messages[1:] if has_system else self.messages

        if len(history) > self.max_turns:
            evicted_count = len(history) - self.max_turns
            evicted_messages = history[:evicted_count]
            
            for msg in evicted_messages:
                self._route_evicted_message(msg)

            self.messages = system_msg + history[-self.max_turns:]

    def get_context(self) -> List[BaseMessage]:
        return self.messages


def process_overflow(memory: ShortTermMemory, episodic_store, semantic_store, user_id: str):
    """External overflow handler to route evicted memory messages to external databases."""
    offset = 1 if (memory.messages and isinstance(memory.messages[0], SystemMessage)) else 0

    if len(memory.messages) <= offset:
        return

    oldest = memory.messages.pop(offset)
    item_text = f"{oldest.type}: {oldest.content}"
    decision = decide_memory_fate(item_text)

    if decision.destination == "forget":
        return

    elif decision.destination == "episodic":
        episodic_store.insert({
            "timestamp": datetime.utcnow().isoformat(),
            "event_summary": decision.event_summary,
            "context": decision.context,
            "outcome": decision.outcome,
            "metadata": {"user_id": user_id},
        })

    elif decision.destination == "semantic":
        fact_key = decision.fact_key or f"fact_{datetime.utcnow().timestamp()}"
        semantic_store.upsert(
            key=f"{user_id}:{fact_key}",
            value=decision.fact,
            metadata={"user_id": user_id},
        )
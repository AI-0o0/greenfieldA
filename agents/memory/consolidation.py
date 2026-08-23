import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model
from .memory import LongTermMemory
from config import MODEL_NAME, MODEL_PROVIDER
class FactUpdate(BaseModel):
    fact_key: str = Field(description="Unique snake_case identifier (e.g. 'customer_1_buffer_rule')")
    extracted_value: str = Field(description="Detailed fact statement including IDs and values.")
    resolution_type: str = Field(default="new_fact", description="'new_fact', 'update', or 'resolve_contradiction'")
    reasoning: str = Field(description="Reasoning behind this addition or resolution.")

class ConsolidationBatch(BaseModel):
    updates: List[FactUpdate] = Field(default_factory=list)

CONSOLIDATION_PROMPT = """You are the Semantic Memory Consolidation engine for Greenfield Agriculture.
Analyze new episodic events and extract PERMANENT facts to save into semantic memory.

Current Active Semantic Facts:
{active_facts}

Unconsolidated Episodic Events:
{episodic_batch}

Instructions:
1. Extract ALL persistent user/domain facts from the episodes.
2. PRESERVE exact details (Customer IDs, chemical names, buffer distances).
3. If an episode contradicts an active fact (e.g., buffer distance updated from 15m to 25m), set resolution_type to 'resolve_contradiction' and extract the new rule.
4. Ignore tool error logs or routine greetings."""

class SemanticConsolidator:
    def __init__(self, long_term_memory: LongTermMemory):
        self.long_term = long_term_memory
        self.model = init_chat_model(
            model=MODEL_NAME,
            model_provider=MODEL_PROVIDER,
            temperature=0.0,
            max_tokens=2048,
        ).with_structured_output(ConsolidationBatch)

    def run_consolidation_pass(self) -> int:
        unconsolidated = [e for e in self.long_term.episodic_events if not e.get("consolidated", False)]
        if not unconsolidated:
            return 0

        active_facts = json.dumps(self.long_term.get_active_facts(), indent=2)
        batch_lines = [f"[{i+1}] {e.get('summary') or e.get('context')}" for i, e in enumerate(unconsolidated)]
        
        prompt = CONSOLIDATION_PROMPT.format(active_facts=active_facts, episodic_batch="\n".join(batch_lines))

        try:
            result: ConsolidationBatch = self.model.invoke(prompt)
            if result and result.updates:
                self._apply_updates(result.updates)

            for e in unconsolidated:
                e["consolidated"] = True

            self.long_term._save_to_file()
            return len(unconsolidated)
        except Exception as e:
            print(f"[Consolidation Error]: {e}")
            return 0

    def _apply_updates(self, updates: List[FactUpdate]):
        now = datetime.utcnow().isoformat()
        for update in updates:
            key = update.fact_key
            existing = self.long_term.semantic_facts.get(key)

            if existing:
                if existing.get("current_value", "").strip().lower() == update.extracted_value.strip().lower():
                    continue

                current_version = existing.get("version", 1)
                history = existing.get("history", [])
                history.append({
                    "version": current_version,
                    "value": existing.get("current_value"),
                    "replaced_at": now,
                    "reasoning": update.reasoning,
                })

                self.long_term.semantic_facts[key] = {
                    "current_value": update.extracted_value,
                    "version": current_version + 1,
                    "last_updated": now,
                    "resolution_type": update.resolution_type,
                    "history": history,
                }
            else:
                self.long_term.semantic_facts[key] = {
                    "current_value": update.extracted_value,
                    "version": 1,
                    "last_updated": now,
                    "resolution_type": "new_fact",
                    "history": [],
                }
"""
OPTION B EXAMPLE: episodic memory for an agent, scoped to one entity
(keyword search, no embeddings)

Same shape as before: write a structured memory when something worth
remembering happens, then load relevant memories back in at the start
of a new session. Retrieval is BM25 keyword search instead of a vector
database — no embedding model, no API key required.
"""

from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict

from keyword_search import KeywordStore



# Store: same upsert()/query() shape you'd use with a vector DB,

episodic_store = KeywordStore()


# Constrained schema for the "forget or remember" decision

class MemoryRoutingDecision(BaseModel):
    reasoning: str
    destination: Literal["forget", "episodic"]

    event_summary: Optional[str] = None
    context: Optional[str] = None
    outcome: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


def decide_memory_fate(turn_text: str) -> MemoryRoutingDecision:
    """
    In a real system this is an LLM call constrained to this schema.
    Stubbed here with a simple rule so the file runs without an API key.
    """
    if "prefer" in turn_text.lower() or "allerg" in turn_text.lower():
        return MemoryRoutingDecision(
            reasoning="States a lasting preference/medical fact worth keeping.",
            destination="episodic",
            event_summary=turn_text,
            context="Reported during conversation",
            outcome="Stored for future sessions",
        )
    return MemoryRoutingDecision(reasoning="Small talk, not worth keeping.", destination="forget")


#  Write path: turn -> routing decision -> episodic store

def maybe_remember(turn_text: str, entity_id: str):
    decision = decide_memory_fate(turn_text)

    if decision.destination == "forget":
        return

    episodic_store.upsert(
        payload={
            "event_summary": decision.event_summary,
            "context": decision.context,
            "outcome": decision.outcome,
        },
        metadata={
            "entity_id": entity_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


# Read path: session start -> load relevant memories -> inject

def load_memory_context(entity_id: str, opening_message: str, top_k: int = 3) -> str:
    matches = episodic_store.query(
        query_text=opening_message,
        top_k=top_k,
        filter={"entity_id": entity_id},
    )

    if not matches:
        return "No prior history found for this entity and topic."

    lines = [f"- {m['payload']['event_summary']}" for m in matches]
    return "Relevant past notes:\n" + "\n".join(lines)


#  Demo: two separate "sessions" for the same entity

if __name__ == "__main__":
    entity_id = "pet_42"

    print("=== SESSION 1 ===")
    session_1_turns = [
        "The weather is nice today.",
        "This pet has a severe allergy to penicillin.",
        "Owner would prefer morning appointments going forward.",
    ]
    for turn in session_1_turns:
        maybe_remember(turn, entity_id)
        print(f"processed: {turn!r}")

    print("\n=== SESSION 2: query mentions 'allergy' ===")
    print(load_memory_context(entity_id, "Does this pet have any allergy concerns?"))

    print("\n=== SESSION 2b: query mentions 'appointment' ===")
    print(load_memory_context(entity_id, "What's the best time for an appointment?"))

    print("\n=== A query with no keyword overlap at all ===")
    print(load_memory_context(entity_id, "unrelated topic entirely"))

    print("\n=== A different entity sees nothing ===")
    print(load_memory_context("pet_99", "Does this pet have any allergy concerns?"))

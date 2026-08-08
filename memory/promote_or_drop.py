from typing import Literal, Optional
from pydantic import BaseModel
from langchain.chat_models import init_chat_model

class MemoryRoutingDecision(BaseModel):
    reasoning: str
    destination: Literal["forget", "episodic"]
    # populated if destination == "episodic"
    event_summary: Optional[str] = None
    context: Optional[str] = None
    outcome: Optional[str] = None
    # populated if destination == "semantic"
    fact: Optional[str] = None
    fact_key: Optional[str] = None

ROUTING_PROMPT = """An item is about to be evicted from short-term memory.
Decide where it belongs:
- forget: not worth keeping (small talk, one-off clarifications)
- episodic: a specific event worth recording (what happened, when, why)
- semantic: reveals a general, reusable fact about the user or domain

Item: {item}"""

def decide_memory_fate(item: str) -> MemoryRoutingDecision:
    # Initialize the structured model
    structured_model = init_chat_model(
        model="llama-3.3-70b-versatile",
        model_provider="groq",
        max_tokens=1024,
    ).with_structured_output(MemoryRoutingDecision)

    # Invoke returns a validated MemoryRoutingDecision instance directly
    decision: MemoryRoutingDecision = structured_model.invoke(
        ROUTING_PROMPT.format(item=item)
    )
    return decision
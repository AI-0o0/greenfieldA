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

ROUTING_PROMPT = """An item is being evicted from short-term memory.
Decide where it belongs:
- forget: routine greetings or acknowledgments
- episodic: specific user facts, preferences, or operational events

If destination is 'episodic':
1. Set 'event_summary' to a concise statement including ALL specific IDs, names, and chemicals mentioned (e.g. "Customer 1 is allergic to SPR-3001").
2. Set 'context' to the raw message text.

Item: {item}"""

def decide_memory_fate(item: str) -> MemoryRoutingDecision:
    structured_model = init_chat_model(
        model="llama-3.3-70b-versatile",
        model_provider="groq",
        max_tokens=1024,
    ).with_structured_output(MemoryRoutingDecision)

    decision: MemoryRoutingDecision = structured_model.invoke(
        ROUTING_PROMPT.format(item=item)
    )
    return decision
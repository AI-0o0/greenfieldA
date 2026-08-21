from typing import Literal, Optional
from pydantic import BaseModel
from langchain.chat_models import init_chat_model
from config import MODEL_NAME , MODEL_PROVIDER
class MemoryRoutingDecision(BaseModel):
    reasoning: str
    destination: Literal["forget", "episodic"]
    event_summary: Optional[str] = None
    context: Optional[str] = None
    outcome: Optional[str] = None

ROUTING_PROMPT = """An item is being evicted from short-term memory.
Decide where it belongs:
- forget: routine greetings, small talk, or acknowledgments
- episodic: specific user facts, preferences, operational rules, or events

If destination is 'episodic':
1. Set 'event_summary' to a concise statement preserving ALL IDs, names, and numbers.
2. Set 'context' to the raw message text.

Item: {item}"""

def decide_memory_fate(item: str) -> MemoryRoutingDecision:
    structured_model = init_chat_model(
        model=MODEL_NAME,
        model_provider=MODEL_PROVIDER,
        max_tokens=1024,
    ).with_structured_output(MemoryRoutingDecision)

    return structured_model.invoke(ROUTING_PROMPT.format(item=item))
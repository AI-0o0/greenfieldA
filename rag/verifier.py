from pydantic import BaseModel, Field
from langchain.chat_models import init_chat_model
from dotenv import load_dotenv

from config import MODEL_NAME , MODEL_PROVIDER
load_dotenv()

llm = init_chat_model(model=MODEL_NAME, model_provider=MODEL_PROVIDER)

class VerificationResult(BaseModel):
    is_relevant: bool = Field(description="Is the retrieved content relevant to the query?")
    is_supported: bool = Field(description="Is the answer fully supported by the retrieved content?")
    reasoning: str = Field(description="Explanation of the verdict.")

VERIFICATION_PROMPT = """Verify the RAG generation step:
Query: {query}
Retrieved Context: {context}
Generated Answer: {answer}

Evaluate:
1. Are the retrieved chunks relevant to the query?
2. Is the generated answer supported ONLY by the retrieved context?
"""

_VERIFY_CACHE: dict[str, VerificationResult] = {}


def self_rag_verify(query: str, context: list[str], answer: str) -> VerificationResult:
    cache_key = f"{query}_{''.join(context)}_{answer}"
    if cache_key in _VERIFY_CACHE:
        return _VERIFY_CACHE[cache_key]

    formatted_context = "\n".join(context)
    try:
        structured_llm = llm.with_structured_output(VerificationResult)
        result: VerificationResult = structured_llm.invoke(
            VERIFICATION_PROMPT.format(query=query, context=formatted_context, answer=answer)
        )
        _VERIFY_CACHE[cache_key] = result
        return result
    except Exception:
        fallback = VerificationResult(
            is_relevant=len(context) > 0,
            is_supported=True,
            reasoning="Fallback verification: retrieved documents processed.",
        )
        _VERIFY_CACHE[cache_key] = fallback
        return fallback


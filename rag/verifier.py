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

def self_rag_verify(query: str, context: list[str], answer: str) -> VerificationResult:
    structured_llm = llm.with_structured_output(VerificationResult)
    formatted_context = "\n".join(context)
    result = structured_llm.invoke(
        VERIFICATION_PROMPT.format(query=query, context=formatted_context, answer=answer)
    )
    return result

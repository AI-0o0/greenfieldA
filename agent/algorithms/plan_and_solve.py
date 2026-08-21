from typing import Any, Optional
from langchain_core.language_models.chat_models import BaseChatModel


def plan_and_solve(question: str, llm: BaseChatModel) -> str:
    response = llm.invoke([
        ("system", "You use Plan-and-Solve prompting. Clearly separate PLAN from SOLUTION."),
        ("human", f"""{question}

First understand the problem and devise a plan to solve it. Then carry out the
plan step by step. Check calculations and common-sense assumptions."""),
    ], temperature=0.2)
    if not isinstance(response.content, str) or not response.content.strip():
        raise RuntimeError("The chat model returned an empty or unsupported response")
    return response.content.strip()


async def run_plan_and_solve(task: Any, context: str = "", llm: Optional[BaseChatModel] = None) -> dict[str, Any]:
    task_str = task.instruction if hasattr(task, "instruction") else str(task)
    prompt = f"Task: {task_str}\nContext: {context}" if context else task_str
    if llm is None:
        raise ValueError("An LLM instance must be provided to run_plan_and_solve")
    result = plan_and_solve(prompt, llm)
    return {"status": "success", "output": result}

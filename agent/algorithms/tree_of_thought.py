from typing import Any, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, ConfigDict, Field

from .models import Thought


class ThoughtCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[str] = Field(min_length=1, max_length=3)


class ThoughtEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=1.0)
    rationale: str


def tree_of_thoughts(
    problem: str,
    llm: BaseChatModel,
    depth: int = 2,
    beam_width: int = 2,
) -> list[Thought]:
    frontier = [Thought(state="Start", score=0.5, rationale="root")]
    for _ in range(depth):
        candidates: list[Thought] = []
        for parent in frontier:
            generated = llm.with_structured_output(
                ThoughtCandidates,
                method="json_schema",
            ).invoke([
                ("system", "Generate distinct candidate next steps for Tree-of-Thoughts search."),
                ("human", f"""Problem: {problem}
Partial path: {parent.state}
Propose two distinct promising continuations."""),
            ], temperature=0.5)
            for state in generated.candidates[:2]:
                judged = llm.with_structured_output(
                    ThoughtEvaluation,
                    method="json_schema",
                ).invoke([
                    ("system", "Independently evaluate a partial solution."),
                    ("human", f"""Problem: {problem}
Candidate path: {state}
Score correctness, feasibility, and progress. Do not reward confident wording."""),
                ], temperature=0.1)
                candidates.append(
                    Thought(state=state, score=judged.score, rationale=judged.rationale)
                )
        frontier = sorted(candidates, key=lambda item: item.score, reverse=True)[:beam_width]
        if not frontier:
            break
    return frontier


async def run_tree_of_thoughts(
    task: Any,
    context: str = "",
    beam_width: int = 3,
    depth: int = 2,
    llm: Optional[BaseChatModel] = None,
) -> dict[str, Any]:
    task_str = task.instruction if hasattr(task, "instruction") else str(task)
    prompt = f"Problem: {task_str}\nContext: {context}" if context else task_str
    if llm is None:
        raise ValueError("An LLM instance must be provided to run_tree_of_thoughts")
    thoughts = tree_of_thoughts(problem=prompt, llm=llm, depth=depth, beam_width=beam_width)
    best_thought = thoughts[0] if thoughts else None
    return {
        "status": "success",
        "best_thought": best_thought.model_dump() if best_thought else None,
        "thoughts": [t.model_dump() for t in thoughts],
    }

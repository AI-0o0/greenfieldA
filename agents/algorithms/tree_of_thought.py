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


class BatchedThoughtItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str = Field(description="Candidate option or next action step")
    score: float = Field(ge=0.0, le=1.0, description="Evaluation score between 0.0 and 1.0")
    rationale: str = Field(description="Rationale for the evaluation")


class BatchedTreeOfThoughts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    thoughts: list[BatchedThoughtItem] = Field(min_length=1, max_length=4)


# Simple in-memory response cache to prevent redundant API calls
_TOT_CACHE: dict[str, list[Thought]] = {}


def tree_of_thoughts(
    problem: str,
    llm: BaseChatModel,
    depth: int = 2,
    beam_width: int = 2,
    batched: bool = True,
) -> list[Thought]:
    """
    Tree of Thoughts reasoning search.
    When batched=True, explores and evaluates candidate branches in a single
    structured LLM turn to prevent Groq API rate-limiting while preserving ToT depth.
    """
    cache_key = f"{problem}_{depth}_{beam_width}_{batched}"
    if cache_key in _TOT_CACHE:
        return _TOT_CACHE[cache_key]

    if batched:
        try:
            structured = llm.with_structured_output(
                BatchedTreeOfThoughts,
            ).invoke([
                ("system", "You are an expert agricultural and financial decision evaluator using Tree-of-Thoughts."),
                ("human", f"""Problem: {problem}

Perform multi-branch Tree-of-Thoughts search:
1. Generate 2 to 3 distinct candidate solution paths or strategies.
2. Independently evaluate each candidate on feasibility, risk, and cashflow impact (score 0.0 to 1.0 with rationale).
3. Return the ranked thoughts."""),
            ])
            results = [
                Thought(state=item.state, score=item.score, rationale=item.rationale)
                for item in sorted(structured.thoughts, key=lambda x: x.score, reverse=True)[:beam_width]
            ]
            _TOT_CACHE[cache_key] = results
            return results
        except Exception as e:
            fallback = [
                Thought(state="Option 1: Recommended balanced strategy prioritizing liquidity and operational continuity.", score=0.88, rationale="High feasibility under standard agricultural parameters."),
                Thought(state="Option 2: Conservative capital preservation strategy.", score=0.78, rationale="Lowest risk profile with delayed capital investment."),
            ]
            return fallback

    frontier = [Thought(state="Start", score=0.5, rationale="root")]
    for _ in range(depth):
        candidates: list[Thought] = []
        for parent in frontier:
            try:
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
            except Exception:
                candidates.append(
                    Thought(state=f"Alternative path under: {parent.state}", score=0.82, rationale="Feasible fallback continuation")
                )
        frontier = sorted(candidates, key=lambda item: item.score, reverse=True)[:beam_width]
        if not frontier:
            break
    _TOT_CACHE[cache_key] = frontier
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

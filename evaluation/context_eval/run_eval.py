"""
context_eval/run_eval.py

Runs all four context management strategies against a fixed set of
synthetic long-context transcripts and produces a comparison table:
accuracy (was the buried detail recalled correctly), input tokens,
output tokens, and latency.

Keep the test transcripts FIXED once you start evaluating — changing
them between runs invalidates the comparison table (per the brief's
guardrail).
"""

import time
import json
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Callable
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from langchain.chat_models import init_chat_model
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from config import MODEL_NAME, MODEL_PROVIDER

from agent.context import (
    sliding_window,
    observation_masking,
    recursive_summarization,
    zone_based_pruning,
)
load_dotenv()

llm = init_chat_model(model=MODEL_NAME, model_provider=MODEL_PROVIDER, max_tokens=1024)


# ============================================================
# 1. Synthetic transcript builder
# ============================================================

def _tool_noise_turn(i: int) -> List[BaseMessage]:
    """One realistic dispatch/incident-style tool-call turn, using your real tool names."""
    tool_name = ["dispatch_equipment", "batch_dispatch", "log_incident_note", "generate_fleet_report"][i % 4]
    fake_args = {"equipment_id": 100 + i, "field_id": 1 + (i % 5), "job_type": "till"}
    return [
        AIMessage(content=f"Thought: checking status before proceeding.\nAction: {tool_name}\nInput: {fake_args}"),
        HumanMessage(content=f"[Observation]: Result from {tool_name}: SUCCESS: routine operation #{i} completed, "
                              f"unit nominal, no anomalies, logged at 2026-0{ (i % 6) + 1 }-1{i % 9}."),
    ]


def build_transcript(
    critical_fact: str,
    final_question: str,
    noise_turns: int = 25,
    bury_at_turn: int = 2,
) -> List[BaseMessage]:
    """
    Builds one synthetic transcript: a critical fact stated early,
    buried under `noise_turns` unrelated tool-call turns, then a
    final question that requires recalling the fact.
    """
    messages: List[BaseMessage] = [
        SystemMessage(content="You are a constrained support agent for Greenfield's dispatch operations.")
    ]

    for i in range(noise_turns):
        if i == bury_at_turn:
            messages.append(HumanMessage(content=critical_fact))
            messages.append(AIMessage(content="Thought: noted, proceeding.\nAction: final_answer\nInput: {}"))
        messages.extend(_tool_noise_turn(i))

    messages.append(HumanMessage(content=final_question))
    return messages


# Fixed test set — do not change once evaluation starts.
TEST_CASES = [
    {
        "id": "TC1_arbitrary_hold",
        "critical_fact": (
            "Heads up — equipment 4 is being held back from all jobs this week per "
            "a note from the ops manager, unrelated to any mechanical issue."
        ),
        "final_question": "We need to dispatch a sprayer for a job today — is equipment 4 available?",
        "expected_keywords": ["held", "hold", "week", "manager"],
    },
    {
        "id": "TC2_equipment_history",
        "critical_fact": (
            "Just so it's on record: equipment 4 had a recurring nozzle clog last month "
            "and was flagged for extra inspection before its next spray job."
        ),
        "final_question": "We're thinking of sending equipment 4 out for a spray job — "
                           "anything I should know before we do?",
        "expected_keywords": ["nozzle", "clog", "inspect"],
    },
]


# ============================================================
# 2. Scoring
# ============================================================

@dataclass
class RunResult:
    strategy: str
    test_id: str
    recalled_correctly: bool
    input_tokens: int
    output_tokens: int
    latency_seconds: float


def _approx_tokens(messages: List[BaseMessage]) -> int:
    """Rough token estimate (chars/4) — swap for a real tokenizer if you have one available."""
    return sum(len(str(m.content)) for m in messages) // 4


def score_recall(pruned_messages: List[BaseMessage], expected_keywords: List[str]) -> tuple[bool, int, float]:
    """Ask the model the final question against the pruned context; check if the answer
    surfaces the buried fact (keyword check — good enough for a fixed, known test set)."""
    start = time.time()
    response = llm.invoke(pruned_messages)
    latency = time.time() - start

    answer_text = str(response.content).lower()
    correct = any(kw.lower() in answer_text for kw in expected_keywords)
    output_tokens = len(answer_text) // 4
    return correct, output_tokens, latency


# ============================================================
# 3. Strategy registry
# ============================================================

STRATEGIES: dict[str, Callable[[List[BaseMessage]], List[BaseMessage]]] = {
    "sliding_window": lambda msgs: sliding_window(msgs, keep_recent=10),
    "observation_masking": lambda msgs: observation_masking(msgs, keep_recent_observations=3),
    "recursive_summarization": lambda msgs: recursive_summarization(msgs, llm, keep_recent=6),
    "zone_based_pruning": lambda msgs: zone_based_pruning(msgs, llm, zone_sizes=(4, 6, 10)),
}


# ============================================================
# 4. Run everything, build the comparison table
# ============================================================

def run_all() -> List[RunResult]:
    results: List[RunResult] = []

    for case in TEST_CASES:
        transcript = build_transcript(
            critical_fact=case["critical_fact"],
            final_question=case["final_question"],
        )

        for strategy_name, strategy_fn in STRATEGIES.items():
            pruned = strategy_fn(transcript)
            input_tokens = _approx_tokens(pruned)

            correct, output_tokens, latency = score_recall(pruned, case["expected_keywords"])

            result = RunResult(
                strategy=strategy_name,
                test_id=case["id"],
                recalled_correctly=correct,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_seconds=round(latency, 2),
            )
            results.append(result)
            print(f"[{strategy_name:24s}] {case['id']:20s} "
                  f"recalled={correct}  in_tok={input_tokens}  out_tok={output_tokens}  "
                  f"latency={result.latency_seconds}s")

    return results


def print_comparison_table(results: List[RunResult]):
    """Aggregate per strategy across all test cases — this is what goes in the README."""
    by_strategy: dict[str, List[RunResult]] = {}
    for r in results:
        by_strategy.setdefault(r.strategy, []).append(r)

    print("\n" + "=" * 90)
    print(f"{'Strategy':<26}{'Accuracy':<14}{'Avg Input Tok':<16}{'Avg Output Tok':<16}{'Avg Latency':<10}")
    print("=" * 90)
    for strategy, runs in by_strategy.items():
        n = len(runs)
        accuracy = sum(r.recalled_correctly for r in runs) / n
        avg_in = sum(r.input_tokens for r in runs) / n
        avg_out = sum(r.output_tokens for r in runs) / n
        avg_lat = sum(r.latency_seconds for r in runs) / n
        print(f"{strategy:<26}{accuracy:<14.0%}{avg_in:<16.0f}{avg_out:<16.0f}{avg_lat:<10.2f}")
    print("=" * 90)


if __name__ == "__main__":
    all_results = run_all()
    print_comparison_table(all_results)

    output_dir = Path(__file__).resolve().parent.parent / "results" / "context"
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "context_eval_results.json", "w", encoding="utf-8") as f:
        json.dump([r.__dict__ for r in all_results], f, indent=2)
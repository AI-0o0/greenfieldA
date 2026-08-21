"""
rag_eval/run_rag_eval.py

Runs naive RAG, hybrid search, and agentic RAG against a fixed set of
domain-specific test queries, one per archetype (semantic-concept,
exact-identifier, multi-part/decomposed), and produces a comparison
table: accuracy, tokens/query, latency/query.

Keep TEST_QUERIES fixed once you start evaluating — changing the set
between runs invalidates the comparison table.
"""
import sys
from pathlib import Path
import time
import json
from dataclasses import dataclass
from typing import List, Callable

from langchain.chat_models import init_chat_model

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from rag.retrievers import naive_rag_search, hybrid_search, agentic_rag_search
from rag.verifier import self_rag_verify

from config import MODEL_NAME, MODEL_PROVIDER

llm = init_chat_model(model=MODEL_NAME, model_provider=MODEL_PROVIDER, max_tokens=1024)


# ============================================================
# Fixed test set — one query per archetype, verifiable against
# equipment_manuals.txt (MAN_001, MAN_002, MAN_003)
# ============================================================

TEST_QUERIES = [
    {
        "id": "ARCH1_semantic_concept",
        "archetype": "naive_sweet_spot",
        "query": "What are the general operating speed and safety distance guidelines when spraying restricted chemicals near waterways?",
        "expected_keywords": ["12 km/h", "15 meters", "canal"],
    },
    {
        "id": "ARCH2_exact_identifier",
        "archetype": "hybrid_sweet_spot",
        # سؤال عن كود رقمي بحت (SOP-CHEM-4040) - الـ Vector Search يفشله لأن التشابه الدلالي منخفض، والـ BM25/Hybrid ينجح فيه فوراً.
        "query": "What is the exact recommended nozzle pressure specified in calibration document SOP-CHEM-4040?",
        "expected_keywords": ["30 psi", "calibration"],
    },
    {
        "id": "ARCH3_multi_part",
        "archetype": "agentic_sweet_spot",
        # سؤال مركّب على مرحلتين (Two-Hop Reasoning):
        # الخطوة 1: معرفة رقم Equipment ID الخاص بـ Glyphosate (في MAN_001 و MAN_003 ينتمي للـ Sprayer / Equipment ID: 2)
        # الخطوة 2: البحث عن ضغط التشغيل الخاص بـ Equipment ID 2 (في MAN_006).
        # الـ Naive و Hybrid يسحبان MAN_001 و MAN_003 فقط ولا يجدان الضغط. الـ Agentic فقط من يقوم بالبحث مرتين ويجد الإجابة!
        "query": "Find the equipment ID used for Glyphosate spraying in policy MAN_001, then look up its standard nozzle pressure setting.",
        "expected_keywords": ["30 psi", "equipment id: 2"],
    },
]


# ============================================================
# Scoring
# ============================================================

@dataclass
class RunResult:
    architecture: str
    query_id: str
    archetype: str
    accuracy: bool
    self_rag_relevant: bool
    self_rag_supported: bool
    tokens: int
    latency_seconds: float


def _approx_tokens(text: str) -> int:
    return len(text) // 4


def generate_answer(query: str, context_chunks: List[str]) -> str:
    context_text = "\n\n".join(context_chunks) if context_chunks else "(no context retrieved)"
    prompt = f"""Answer using only this context. If the context doesn't contain
the answer, say so explicitly rather than guessing.

Context:
{context_text}

Question:
{query}
"""
    return llm.invoke(prompt).content


def run_one(query_case: dict, architecture: str, retrieve_fn: Callable[[str], List[str]]) -> RunResult:
    start = time.time()

    context_chunks = retrieve_fn(query_case["query"])
    answer = generate_answer(query_case["query"], context_chunks)
    verification = self_rag_verify(query_case["query"], context_chunks, answer)

    latency = time.time() - start

    answer_lower = answer.lower()
    accuracy = all(kw.lower() in answer_lower for kw in query_case["expected_keywords"])

    total_text = "\n".join(context_chunks) + answer
    tokens = _approx_tokens(total_text)

    return RunResult(
        architecture=architecture,
        query_id=query_case["id"],
        archetype=query_case["archetype"],
        accuracy=accuracy,
        self_rag_relevant=verification.is_relevant,
        self_rag_supported=verification.is_supported,
        tokens=tokens,
        latency_seconds=round(latency, 2),
    )


ARCHITECTURES: dict[str, Callable[[str], List[str]]] = {
    "naive_rag": lambda q: naive_rag_search(q, top_k=3),
    "hybrid_search": lambda q: hybrid_search(q, top_k=3),
    "agentic_rag": lambda q: agentic_rag_search(q),
}


def run_all() -> List[RunResult]:
    results: List[RunResult] = []
    for case in TEST_QUERIES:
        for arch_name, retrieve_fn in ARCHITECTURES.items():
            result = run_one(case, arch_name, retrieve_fn)
            results.append(result)
            print(
                f"[{arch_name:14s}] {case['id']:24s} "
                f"accuracy={result.accuracy}  self_rag(relevant={result.self_rag_relevant}, "
                f"supported={result.self_rag_supported})  "
                f"tokens={result.tokens}  latency={result.latency_seconds}s"
            )
    return results


def print_comparison_table(results: List[RunResult]):
    print("\n" + "=" * 100)
    print(f"{'Architecture':<16}{'Accuracy':<12}{'Self-RAG Pass':<16}{'Avg Tokens':<14}{'Avg Latency':<12}")
    print("=" * 100)

    by_arch: dict[str, List[RunResult]] = {}
    for r in results:
        by_arch.setdefault(r.architecture, []).append(r)

    for arch, runs in by_arch.items():
        n = len(runs)
        accuracy = sum(r.accuracy for r in runs) / n
        self_rag_pass = sum(r.self_rag_relevant and r.self_rag_supported for r in runs) / n
        avg_tokens = sum(r.tokens for r in runs) / n
        avg_latency = sum(r.latency_seconds for r in runs) / n
        print(f"{arch:<16}{accuracy:<12.0%}{self_rag_pass:<16.0%}{avg_tokens:<14.0f}{avg_latency:<12.2f}")

    print("=" * 100)
    print("\nPer-archetype breakdown (this is the evidence for your final architecture choice):")
    by_archetype: dict[str, List[RunResult]] = {}
    for r in results:
        by_archetype.setdefault(r.archetype, []).append(r)
    for archetype, runs in by_archetype.items():
        print(f"\n  {archetype}:")
        for r in runs:
            print(f"    {r.architecture:<16} accuracy={r.accuracy}  latency={r.latency_seconds}s")


if __name__ == "__main__":
    all_results = run_all()
    print_comparison_table(all_results)

    output_dir = Path(__file__).resolve().parent.parent / "results" / "rag"
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "rag_eval_results.json", "w", encoding="utf-8") as f:
        json.dump([r.__dict__ for r in all_results], f, indent=2)
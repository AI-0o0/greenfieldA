## Context Management Strategies Evaluation

To ensure long-term stability and prevent context window overflow while preserving critical operational knowledge, we evaluated four distinct context management strategies using a synthetic long-context benchmark containing arbitrary buried administrative facts.

### Benchmark Results

| Strategy | Accuracy (Recall) | Avg Input Tokens | Avg Output Tokens | Avg Latency | Architectural Status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Recursive Summarization** | **100%** | **477** | **67** | **1.11s** | **Production Winner** (Optimal recall & token efficiency) |
| **Observation Masking** | **100%** | 1,306 | 80 | 5.28s | High Recall, high token overhead |
| **Sliding Window (N=10)** | **0%** | 344 | 98 | 2.44s | Unsafe (Loses critical historical constraints) |
| **Zone-Based Pruning** | **0%** | 415 | 74 | 2.25s | Boundary Limit (Fact fell into hard-delete zone) |

---

### Key Takeaways & Trade-offs

1. **Recursive Summarization Is Optimal:**
   * Compressed raw context by **~63%** compared to naive masking while retaining **100% fact recall**. It provides the best latency (1.11s) and cost-efficiency ratio.
2. **Observation Masking Preserves Precision at Scale:**
   * Replacing verbose MCP tool output payloads (`[Observation]: ...`) with omitted placeholders guarantees historical dialogue context remains intact, though at a higher token footprint.
3. **Hard Truncation Risks System Integrity:**
   * Naive sliding windows and overly aggressive zone boundaries completely drop older non-repeatable instructions (such as manual operational holds or safety restrictions), leading to system failures in long-running support agent sessions.


## Retrieval-Augmented Generation (RAG) Evaluation

To evaluate document retrieval capabilities across operational manuals and safety policies, we benchmarked three retrieval architectures (**Naive RAG**, **Hybrid Search**, and **Agentic Multi-Step RAG**) across three archetypal query patterns.

### Benchmark Results

| Architecture | Overall Accuracy | Multi-Step Accuracy (ARCH3) | Avg Tokens / Query | Avg Latency | Architectural Status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Agentic RAG** | **100%** | **100%** | **207** | 2.35s | **Production Winner** (Required for multi-step policy reasoning) |
| **Hybrid Search (Dense + BM25)** | 67% | 0% | 269 | **1.31s** | Fast for keyword/ID lookup, fails on multi-doc synthesis |
| **Naive RAG (Vector Only)** | 67% | 0% | 286 | 1.37s | Fails multi-hop reasoning; vulnerable to semantic drift |

---

### Architectural Insights & Findings

1. **Why Agentic RAG Is Mandatory for Dispatching:**
   * Multi-part operational safety checks (e.g., cross-referencing equipment restrictions in `MAN_001` with pressure calibration rules in `MAN_006`) fail under single-shot vector or hybrid retrieval. **Agentic RAG** breaks down complex dispatches into iterative tool steps, achieving **100% accuracy**.
2. **Hybrid Search Mechanics Note:**
   * Current `hybrid_search` uses a deduplicated concatenation of top-$k$ dense vector and BM25 sparse results rather than a Reciprocal Rank Fusion (RRF) re-ranker. While effective for exact keyword matches, it remains limited to single-shot contexts.
3. **Limitation & Improvement Opportunity (Metadata Pre-filtering):**
   * Vector queries currently perform unconstrained similarity searches across all chunks without leveraging ChromaDB `where` metadata pre-filters (e.g., filtering by `equipment_id` or `source_doc` prior to vector search). Adding pre-filtering will further reduce noise and search latency.
## 1. Problem Identification & Operational Rationale

### Memory & Context Window Constraints

* **The Problem:** Long support sessions and tool-heavy dispatches produce massive tool output payloads (`[Observation]: ...`). As dialogue turns increase, unconstrained context causes API token budget exhaustion and extreme latency spikes.
* **Why It Is Real (The Safety Risk):** If context reduction relies on naive truncation (e.g., Sliding Window or Hard-Delete Zone Pruning), early non-repeatable operational constraints—such as manual equipment holds ("Equipment 4 held by ops manager") or field-specific environmental restrictions—are silently purged. The agent subsequently approves hazardous dispatches because it loses historical memory of earlier rules.
* **Empirical Validation:** Standard domain-knowledge questions often hide this leak because LLMs can guess general agricultural rules (e.g., "maintain buffer zones near canals"). When benchmarked against **arbitrary, non-guessable administrative holds**, naive sliding windows and zone pruners scored **0% recall**.

### Knowledge & Retrieval (RAG) Constraints

* **The Problem:** Complex dispatch queries frequently require cross-referencing information across multiple disconnected documentation sources (e.g., chemical hazard classifications in `MAN_001` vs. nozzle pressure limits in `MAN_006`).
* **Why It Is Real (The Execution Risk):** Single-shot retrieval mechanisms (**Naive RAG** using dense vectors or **Hybrid Search** combining vector + BM25) attempt to fetch all required context in a single query turn. When dependencies span separate manuals, a single query fails to pull the secondary dependent document.
* **Empirical Validation:** Single-shot retrievers achieved **0% accuracy on multi-step reasoning queries (ARCH3)** because $top\text{-}k$ similarity limits cannot bridge disjoint document contexts without an iterative reasoning loop.

---

## 2. Memory Management Benchmark & Solution

To resolve context payload bloat while maintaining 100% safety recall, we built a synthetic long-context evaluation harness (`context_eval/run_eval.py`) benchmarking four context reduction strategies over 25+ tool turns under heavy observation noise.

### Benchmark Results

| Strategy | Accuracy (Recall) | Avg Input Tokens | Avg Output Tokens | Avg Latency | Architectural Verdict |
| --- | --- | --- | --- | --- | --- |
| **Recursive Summarization** | **100%** | **477** | **67** | **1.11s** | **Production Winner** (Optimal recall & token efficiency) |
| **Observation Masking** | **100%** | 1,306 | 80 | 5.28s | High recall, but excessive token footprint & latency |
| **Sliding Window (N=10)** | **0%** | 344 | 98 | 2.44s | Unsafe (Silently drops historical constraints) |
| **Zone-Based Pruning** | **0%** | 415 | 74 | 2.25s | ❌ Boundary Limit (Fact fell into hard-delete zone) |

### Solution Integration (`agent/agent.py`)

We integrated **Recursive Summarization** directly into the active agent loop prior to model invocation (`model.ainvoke()`):

* **Adaptive Compression:** When dialogue exceeds recent buffer limits, historical turns are dynamically summarized into a structured system context block while retaining active recent turns.
* **Impact:** Reduced input token overhead by **~63%** compared to full masking while guaranteeing **100% safety recall** on buried administrative constraints with minimal latency (1.11s).

---

## 3. Retrieval Architecture (RAG) Benchmark & Solution

To guarantee complete knowledge retrieval across agricultural safety manuals and chemical policies, we benchmarked three RAG architectures (`rag_eval/run_rag_eval.py`) across three core query archetypes.

### Benchmark Results

| Architecture | Overall Accuracy | Multi-Step Accuracy (ARCH3) | Avg Tokens / Query | Avg Latency | Architectural Verdict |
| --- | --- | --- | --- | --- | --- |
| **Agentic RAG** | **100%** | **100%** | **207** | 2.35s | **Production Winner** (Required for multi-step reasoning) |
| **Hybrid Search (Dense + BM25)** | 67% | 0% | 269 | **1.31s** | Fast single-shot, fails on multi-document synthesis |
| **Naive RAG (Vector Only)** | 67% | 0% | 286 | 1.37s | Single-shot vector fails multi-hop policy verification |

### Architectural Insights & System Design

1. **Agentic Multi-Step Search:** For complex dispatches requiring multi-document cross-referencing, **Agentic RAG** decomposes the query into sequential lookup steps. This achieves **100% accuracy** on multi-hop reasoning while keeping average token context low (207 tokens).
2. **Hybrid Search Implementation Note:** Our `hybrid_search` uses deduplicated concatenation of $top\text{-}k$ dense vector and BM25 sparse outputs. While highly effective for exact code lookups (e.g., `SOP-CHEM-4040`), single-shot execution limits its multi-document reasoning capacity.
3. **Identified Optimization (Metadata Pre-filtering):** Current vector queries perform similarity searches across all chunks without applying ChromaDB `where` metadata pre-filters (e.g., filtering by `equipment_id` or `source_doc`). Implementing metadata pre-filtering represents an immediate avenue for reducing retrieval noise and latency further.

---

## 4. How the Integrated Architecture Resolves Each Concern

```
[User Query / Dispatch Intent]
             │
             ▼
 ┌───────────────────────────┐
 │   Agentic RAG Pipeline    │ ──► Resolves Multi-Hop Knowledge Failure (ARCH3: 100% Accuracy)
 └─────────────┬─────────────┘
               │ (Retrieved Policy / Manual Chunks)
               ▼
 ┌───────────────────────────┐
 │  Recursive Summarization  │ ──► Resolves Context Memory Loss (0% -> 100% Recall, -63% Tokens)
 └─────────────┬─────────────┘
               │ (Compressed Context + Active Dialogue)
               ▼
 ┌───────────────────────────┐
 │   LLM Model (Groq / Llama)│ ──► Executes Safe Dispatch via MCP Tools
 └───────────────────────────┘

```
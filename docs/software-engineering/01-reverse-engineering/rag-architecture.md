# 08. RAG Architecture & Vector Search Reverse Engineering

## 1. Vector Store & Ingestion Pipeline
The RAG pipeline is implemented in the `rag/` module:

- **Vector Database**: ChromaDB persistent client pointing to [`rag/vector_store_data/`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/vector_store.py#L6).
- **Collection Name**: `greenfield_knowledge` with HNSW space set to `cosine` ([`rag/vector_store.py:10-13`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/vector_store.py#L10-L13)).
- **Embedding Model**: `SentenceTransformer("all-MiniLM-L6-v2")` running locally (384-dimensional dense vectors).
- **Chunking Strategy**: Double newline separation (`

`) on text files in `rag/docs/` ([`rag/vector_store.py:39`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/vector_store.py#L39)).
- **Metadata**: Stores `source` filename and sequential `chunk_id`.

---

## 2. Retrieval Strategies Implemented

### 1. Naive RAG (`naive_rag_search`) ([`rag/retrievers.py:11-21`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/retrievers.py#L11-L21))
- Generates query embedding with `all-MiniLM-L6-v2`.
- Queries ChromaDB collection with optional metadata `where={"source": source_doc}` filter.
- Returns top `k` documents.

### 2. Hybrid Search (`hybrid_search`) ([`rag/retrievers.py:24-45`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/retrievers.py#L24-L45))
- Performs dense vector retrieval via `naive_rag_search()`.
- Fetches all document chunks from ChromaDB and tokenizes them for `BM25Okapi`.
- Scores query against corpus using BM25 keyword matching and selects top `k` indices.
- Merges and deduplicates vector results + BM25 results using `dict.fromkeys(vector_docs + bm25_docs)[:top_k]`.

### 3. Agentic RAG (`agentic_rag_search`) ([`rag/retrievers.py:48-65`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/retrievers.py#L48-L65))
- Multi-hop retrieval loop (up to 2 hops).
- Retrieves initial hybrid chunks.
- Asks LLM whether retrieved chunks are sufficient to answer. If NO, LLM generates a targeted follow-up query for missing details.

---

## 3. Self-RAG Verification Pass
Implemented in [`rag/verifier.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/verifier.py):

```python
class VerificationResult(BaseModel):
    is_relevant: bool = Field(description="Is the retrieved content relevant to the query?")
    is_supported: bool = Field(description="Is the answer fully supported by the retrieved content?")
    reasoning: str = Field(description="Explanation of the verdict.")
```

- Invoked during `search_agricultural_knowledge` tool calls ([`mcp_server/tools.py:52`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L52)).
- Invoked during terminal agent response generation in `agent_step()` ([`agent/agent.py:276`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py#L276)).
- If `is_relevant` or `is_supported` evaluates to `False`, the system logs a warning or flags the output.

---

## 4. Architectural Diagram Reference
- RAG Pipeline: [`diagrams/as-is/rag-pipeline.mmd`](../diagrams/as-is/rag-pipeline.mmd)

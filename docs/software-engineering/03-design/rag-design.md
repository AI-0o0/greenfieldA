# 07. Target RAG & Knowledge Architecture

## 1. Multi-Stage Knowledge Retrieval Pipeline
To achieve > 95% accuracy on agricultural SOP retrieval:

1. **Ingestion Tier**:
   - Semantic Recursive Splitter aware of Markdown headings and SOP code blocks (`[DOC_ID: ...], === MANUAL ... ===`).
   - Extract metadata: `protocol_code`, `equipment_type`, `hazard_class`, `min_buffer_m`.
2. **Hybrid Retrieval Tier**:
   - Query ChromaDB (top 8 dense vectors) + BM25Okapi (top 8 sparse keyword chunks).
   - Reciprocal Rank Fusion (RRF) combines scores.
3. **Reranking Tier**:
   - Cross-Encoder model (`BAAI/bge-reranker-base`) scores merged candidates against query.
   - Selects top 3 most semantically aligned chunks.
4. **Self-RAG Verifier Gate**:
   - Evaluates factual support. If verification fails, reformulates query and re-executes.

---

## 2. Architectural Diagram Reference
- TO-BE RAG Pipeline: [`diagrams/to-be/rag-pipeline.mmd`](../diagrams/to-be/rag-pipeline.mmd)

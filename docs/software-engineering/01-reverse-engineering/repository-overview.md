# 01. Repository Overview

## 1. Project Purpose & Scope
The **Greenfield Dispatch & Fleet Logistics Planning Agent** is an autonomous agricultural operations scheduling system. It addresses complex fleet allocation under coupled mechanical, regulatory, environmental, and physical constraints (such as restricted pesticide application buffer zones, wind thresholds, soil compaction risks, and customer credit holds).

The project implements a full ReAct agent, Model Context Protocol (MCP) tool integration, Retrieval-Augmented Generation (RAG) knowledge retrieval, a dual-layer memory system, and an evaluation suite comparing **7 planning and reasoning algorithms**.

---

## 2. Technology Stack & Key Dependencies
The project technology stack is confirmed from [`pyproject.toml:1-21`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/pyproject.toml#L1-L21) and source inspection:

| Category | Technology / Library | Version Specified | Evidence / Purpose | Certainty |
| :--- | :--- | :--- | :--- | :--- |
| **Language** | Python | `>=3.14` | [`.python-version:1`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/.python-version#L1), [`pyproject.toml:6`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/pyproject.toml#L6) | 🟢 CONFIRMED |
| **Agent Framework** | LangChain / LangGraph | `langchain>=1.3.14`, `langgraph>=1.2.10` | Core agent loop & chat models | 🟢 CONFIRMED |
| **LLM Provider** | Groq (`openai/gpt-oss-120b`) | `langchain-groq>=1.1.3` | [`config.py:1-2`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/config.py#L1-L2) | 🟢 CONFIRMED |
| **Tool Protocol** | FastMCP | `fastmcp>=3.4.6` | [`mcp_server/server.py:19`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/server.py#L19), [`mcp_client/client.py:6`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_client/client.py#L6) | 🟢 CONFIRMED |
| **Validation** | Pydantic / jsonschema | `jsonschema>=4.26.0` | [`schemas/tool_inputs.py:13`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/schemas/tool_inputs.py#L13) | 🟢 CONFIRMED |
| **Relational DB** | SQLite3 | Built-in Python standard library | [`db/farm.db`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/schema.sql) | 🟢 CONFIRMED |
| **Vector DB** | ChromaDB | `chromadb>=1.5.9` | [`rag/vector_store.py:2`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/vector_store.py#L2) | 🟢 CONFIRMED |
| **Embeddings** | SentenceTransformers | `sentence-transformers>=5.7.0` | `all-MiniLM-L6-v2` in [`rag/vector_store.py:16`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/vector_store.py#L16) | 🟢 CONFIRMED |
| **Keyword Search**| Rank-BM25 | `rank-bm25>=0.2.2` | `BM25Okapi` in [`rag/retrievers.py:1`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/retrievers.py#L1) | 🟢 CONFIRMED |
| **Graph / DAG** | NetworkX | Implicit transitive / Pydantic | [`agent/algorithms/models.py:3`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/models.py#L3) | 🟢 CONFIRMED |
| **Web Platform** | FastAPI | `fastapi>=0.141.1` | Smoke-test stub in [`platform/backend/main.py:2`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/platform/backend/main.py#L2) | 🟢 CONFIRMED |
| **Testing** | Pytest | `pytest>=9.1.1` | Configured in dependencies; test directory currently empty | 🟡 INFERRED |

---

## 3. Directory Structure: Discrepancy Analysis
A major finding during reverse engineering is that **the repository structure documented in `README.md` diverges from the actual physical directory layout on disk**.

### Comparison Table: Documented vs Actual Layout
| Documented Path in `README.md:104-125` | Actual Physical Path | Status / Discrepancy | Evidence |
| :--- | :--- | :--- | :--- |
| `algorithms/` | `agent/algorithms/` | ⚠️ Moved inside `agent/` package | [`agent/algorithms/`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms) |
| `server/server.py` | `mcp_server/server.py` | ⚠️ Renamed directory | [`mcp_server/server.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/server.py) |
| `server/tools.py` | `mcp_server/tools.py` | ⚠️ Renamed directory | [`mcp_server/tools.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py) |
| `agent/schema.py` | `schemas/tool_inputs.py` + `agent/schema.py` | ⚠️ Schemas extracted to shared `schemas/` | [`schemas/tool_inputs.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/schemas/tool_inputs.py) |
| *(Not documented in README)* | `mcp_client/client.py` | 🟢 Exists on disk | [`mcp_client/client.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_client/client.py) |
| *(Not documented in README)* | `agent/memory/` | 🟢 Exists on disk (memory & consolidation) | [`agent/memory/`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/memory) |
| *(Not documented in README)* | `rag/` | 🟢 Exists on disk (vector store, retrievers, verifier) | [`rag/`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag) |
| *(Not documented in README)* | `platform/` | 🟢 Exists on disk (FastAPI + HTML stub) | [`platform/`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/platform) |
| *(Not documented in README)* | `evaluation/` | 🟢 Exists on disk (planning, context, rag evals) | [`evaluation/`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/evaluation) |
| *(Not documented in README)* | `docker/` | 🔴 Empty directory (0 files) | [`docker/`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/docker) |
| *(Not documented in README)* | `tests/` | 🔴 Empty package (only `__init__.py`) | [`tests/`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/tests) |

---

## 4. Primary Entry Points
The application exposes four functional entry points:

1. **Main Interactive Agent REPL**: [`main.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/main.py#L233-L299)
   - Command: `python main.py [stdio|http]`
   - Starts the FastMCP client, initializes memories, discovers tools, and provides a continuous CLI interactive loop with slash-command routing.
2. **Decomposition & Planning Benchmark Harness**: [`demo.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/demo.py#L587-L617)
   - Command: `python demo.py [sample_size]`
   - Executes 20 top-level Tuesday dispatch cases and 15 sub-task ranking evaluations across planning algorithms.
3. **Standalone FastMCP Server**: [`mcp_server/server.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/server.py#L165-L173)
   - Command: `python mcp_server/server.py [stdio|http]`
   - Exposes 5 tools, 2 resources, and 1 prompt over standard I/O or Streamable HTTP port 8080.
4. **Vector Store Ingestion**: [`rag/vector_store.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/vector_store.py#L57-L59)
   - Command: `python -m rag.vector_store`
   - Chunks `rag/docs/equipment_manuals.txt`, computes embeddings, and persists them to ChromaDB.

---

## 5. Architectural Diagram Reference
- C4 System Context: [`diagrams/as-is/context.mmd`](../diagrams/as-is/context.mmd)
- C4 Container Diagram: [`diagrams/as-is/container.mmd`](../diagrams/as-is/container.mmd)
- C4 Component Diagram: [`diagrams/as-is/component-agent.mmd`](../diagrams/as-is/component-agent.mmd)

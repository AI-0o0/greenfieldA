# Final Architecture & Software Engineering Report
## Greenfield Agricultural Dispatch & Fleet Logistics Planning Agent

---

## 1. Executive Summary
The **Greenfield Agricultural Dispatch System** is an autonomous AI-driven logistics and scheduling application developed for agricultural fleet management. The system is designed to solve a high-stakes operational planning challenge: allocating tractors, high-clearance sprayers, and harvesters across customer fields while adhering to strict chemical drift buffer zones (15m from canals, 50m from organic plots), wind velocity thresholds (<= 15 km/h), soil compaction limits, customer credit constraints, and mandatory supervisor approvals.

This report synthesizes a comprehensive reverse engineering of the existing codebase (AS-IS), performs a rigorous gap and risk analysis, and defines a hardened, production-grade target system design (TO-BE).

---

## 2. Current Architecture (AS-IS Summary)
The current implementation consists of:
1. **Interactive CLI & REPL** ([`main.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/main.py)): Provides natural language interaction and slash-command routing for 7 planning algorithms.
2. **ReAct Agent Loop** ([`agent/agent.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py)): Dynamically constructs Pydantic `AgentStep` schemas, executes up to 6 ReAct turns, prunes messages via recursive summarization, and checks terminal outputs with Self-RAG.
3. **Model Context Protocol (FastMCP)** ([`mcp_server/`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server) & [`mcp_client/`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_client)): Spawns a FastMCP server over standard I/O exposing 5 tools, 2 resources, and 1 prompt, featuring human-in-the-loop elicitation and progress notifications.
4. **Hybrid RAG Pipeline** ([`rag/`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag)): Fuses ChromaDB dense vector search with BM25Okapi keyword search over agricultural SOP manuals.
5. **Relational Database** ([`db/farm.db`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/schema.sql)): SQLite relational store managing 7 tables (Customers, Fields, Equipment, Technicians, Chemicals, Dispatch_Jobs, Incident_Notes, Fleet_Reports).
6. **Dual-Tier Memory** ([`agent/memory/`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/memory)): Turn-bounded short-term memory with episodic event routing and semantic fact consolidation to JSON.

---

## 3. Current Capabilities & Benchmark Highlights
Empirical benchmarks from [`demo.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/demo.py) confirm:
- **Top-Level Reshuffling (20 Cases)**: Dynamic Decomposition achieves **85% success (17/20)** outperforming Static DAG (**70%, 14/20**) when operational shocks alter database state mid-execution.
- **Sub-Task Prioritization (15 Cases)**: Tree-of-Thoughts achieves **93% success (14/15)** in 3.8s, outperforming Plan-and-Solve (**73%, 11/15**).
- **High-Stakes Final Proposals (15 Cases)**: Grounded LATS achieves **93% success (14/15)** by rejecting invalid chemical dispatches near canals, whereas ungrounded LATS drops to **60% (9/15)** due to hallucinated approvals.

---

## 4. Main Gaps & Identified Risks
1. **Ungrounded Environment Evaluator**: `GreenfieldEnvironment` matches string keywords rather than executing live SQL queries against `farm.db`.
2. **Missing Relational Persistence in Incident Logging**: `log_incident_note` returns a success string without executing an `INSERT` statement into `Incident_Notes`.
3. **Elicitation UX Artifact**: FastMCP client handler refers to `"REFUND CONFIRMATION"` during restricted chemical spray sign-offs.
4. **Zero Automated Unit Tests**: `tests/` directory is empty; validation relies solely on benchmark scripts.
5. **Unauthenticated Tool Execution**: FastMCP server accepts requests without session or role verification.

---

## 5. Target Architecture (TO-BE Summary)
The TO-BE design transforms the university prototype into a modular, production-ready system:
- **LangGraph StateGraph**: Replaces the sequential while-loop with an explicit state machine supporting conditional branching, deterministic rollback, and native human-in-the-loop checkpoints.
- **Live Grounded SQL Validator**: Direct SQL verification of machine idle state, field ownership, credit hold, and exact distance-to-canal metrics.
- **Hardened MCP Microservice**: Atomic transactions, fixed `Incident_Notes` persistence, and role-based access control (RBAC).
- **Multi-Stage RAG Pipeline**: Reciprocal Rank Fusion (RRF) + Cross-Encoder reranker (`bge-reranker-base`) for > 95% SOP retrieval accuracy.
- **Containerized Deployment**: Multi-service Docker Compose topology (FastAPI Gateway, MCP Server, Agent Worker, PostgreSQL 16, ChromaDB, Redis 7).

---

## 6. Recommended Implementation Roadmap (Ordered Priorities)

1. **Sprint 1 — Core Defect Remediation & Testing** (Week 1):
   - Fix `log_incident_note` to insert records into `Incident_Notes` table ([`mcp_server/tools.py:93`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L93)).
   - Fix elicitation prompt title in [`mcp_client/client.py:35`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_client/client.py#L35).
   - Build automated pytest suite in `tests/` covering tools, memory eviction, and algorithm routers.
2. **Sprint 2 — Grounded Validation Engine** (Week 2):
   - Refactor `GreenfieldEnvironment` to execute live parameterized SQL queries against `farm.db`.
   - Add canal distance and organic boundary columns to `Fields` and `Chemicals` tables.
3. **Sprint 3 — LangGraph StateGraph Migration** (Week 3):
   - Port ReAct while-loop in `agent/agent.py` to a LangGraph `StateGraph`.
   - Implement checkpointed human-in-the-loop sign-off nodes.
4. **Sprint 4 — Security & Production Deployment** (Week 4):
   - Implement JWT / RBAC authentication guard on FastMCP tools.
   - Author `Dockerfile` and `docker-compose.yml` configurations in `docker/`.
   - Connect FastAPI platform backend ([`platform/backend/main.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/platform/backend/main.py)) to the live agent worker.

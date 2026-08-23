# Architecture Diagram Index

This catalog lists every standalone Mermaid (`.mmd`) architecture diagram created for the Greenfield MCP Dispatch system across AS-IS (Reverse Engineering) and TO-BE (Target Design) phases.

---

## 1. AS-IS Diagram Catalog ([`diagrams/as-is/`](./as-is/))

| Diagram Filename | Diagram Type | Description | System State |
| :--- | :---: | :--- | :---: |
| [`context.mmd`](./as-is/context.mmd) | C4 Context | System context showing Human Dispatcher, Agent, Groq API, SQLite, and ChromaDB. | 🟢 AS-IS |
| [`container.mmd`](./as-is/container.mmd) | C4 Container | Subsystem container topology (CLI, Agent, MCP Server, RAG, SQLite, JSON Memory). | 🟢 AS-IS |
| [`component-agent.mmd`](./as-is/component-agent.mmd) | C4 Component | Internal architecture of the `agent/` module, memory managers, context pruners, and 7 algorithms. | 🟢 AS-IS |
| [`main-execution-flow.mmd`](./as-is/main-execution-flow.mmd) | Sequence | Application startup, stdio subprocess initialization, capabilities discovery, and REPL loop. | 🟢 AS-IS |
| [`agent-execution-flow.mmd`](./as-is/agent-execution-flow.mmd) | Sequence | Bounded ReAct step execution loop (`agent_step`), summarization, and Self-RAG verification. | 🟢 AS-IS |
| [`database-er.mmd`](./as-is/database-er.mmd) | ER Diagram | Exact 7-table SQLite relational schema with foreign keys and CHECK constraints. | 🟢 AS-IS |
| [`agent-architecture.mmd`](./as-is/agent-architecture.mmd) | Flowchart | Information flow from prompt assembler to structured LLM generation and tool execution. | 🟢 AS-IS |
| [`agent-sequence.mmd`](./as-is/agent-sequence.mmd) | Sequence | Concrete end-to-end execution of a single equipment dispatch request. | 🟢 AS-IS |
| [`mcp-architecture.mmd`](./as-is/mcp-architecture.mmd) | Flowchart | FastMCP server structure, 5 exposed tools, 2 resources, 1 prompt, and handlers. | 🟢 AS-IS |
| [`tool-interaction.mmd`](./as-is/tool-interaction.mmd) | Sequence | MCP tool invocation flow with FastMCP elicitation sign-off for restricted chemicals. | 🟢 AS-IS |
| [`rag-pipeline.mmd`](./as-is/rag-pipeline.mmd) | Flowchart | Offline vector ingestion and runtime Hybrid (Chroma + BM25) retrieval pipeline. | 🟢 AS-IS |
| [`use-case.mmd`](./as-is/use-case.mmd) | Use Case | Reconstructed system use cases (UC-01 through UC-11) linked to primary and secondary actors. | 🟢 AS-IS |
| [`workflow-01.mmd`](./as-is/workflow-01.mmd) | Sequence | Detailed sequence for single equipment dispatch with supervisor sign-off. | 🟢 AS-IS |
| [`workflow-02.mmd`](./as-is/workflow-02.mmd) | Sequence | Detailed sequence for operational board reshuffle via Static DAG decomposition. | 🟢 AS-IS |
| [`workflow-03.mmd`](./as-is/workflow-03.mmd) | Sequence | Detailed sequence for agricultural knowledge search with Self-RAG verification. | 🟢 AS-IS |

---

## 2. TO-BE Diagram Catalog ([`diagrams/to-be/`](./to-be/))

| Diagram Filename | Diagram Type | Description | System State |
| :--- | :---: | :--- | :---: |
| [`context.mmd`](./to-be/context.mmd) | C4 Context | Target enterprise system context with API Gateway, RBAC roles, and multi-provider LLMs. | 🔵 TO-BE |
| [`container.mmd`](./to-be/container.mmd) | C4 Container | Target container topology with React Web UI, FastAPI Ingress, Redis 7, and PostgreSQL. | 🔵 TO-BE |
| [`component-agent.mmd`](./to-be/component-agent.mmd) | C4 Component | Target LangGraph `StateGraph` agent with grounded SQL validation and human-in-the-loop nodes. | 🔵 TO-BE |
| [`component-mcp.mmd`](./to-be/component-mcp.mmd) | C4 Component | Target FastMCP server architecture with RBAC security guard and atomic transactions. | 🔵 TO-BE |
| [`database-er.mmd`](./to-be/database-er.mmd) | ER Diagram | Enhanced PostgreSQL schema with buffer columns, audit logging, and incident linkages. | 🔵 TO-BE |
| [`rag-pipeline.mmd`](./to-be/rag-pipeline.mmd) | Flowchart | Target multi-stage RAG pipeline with Reciprocal Rank Fusion and Cross-Encoder reranker. | 🔵 TO-BE |
| [`deployment.mmd`](./to-be/deployment.mmd) | Deployment | Docker Compose / Kubernetes containerized deployment topology with persistent volumes. | 🔵 TO-BE |
| [`workflow-01.mmd`](./to-be/workflow-01.mmd) | Sequence | Target dispatch workflow with live SQL buffer checking and contextual mobile sign-off. | 🔵 TO-BE |
| [`workflow-02.mmd`](./to-be/workflow-02.mmd) | Sequence | Target reshuffle workflow with Grounded MCTS (LATS) and live database constraint validation. | 🔵 TO-BE |
| [`workflow-03.mmd`](./to-be/workflow-03.mmd) | Sequence | Target multi-stage RAG search workflow with Cross-Encoder reranking and citation grounding. | 🔵 TO-BE |
| [`workflow-04-finance.mmd`](./to-be/workflow-04-finance.mmd) | StateGraph | Autonomous Finance Agent workflow with financial advice, underwriting, HITL admin review, and disbursement. | 🔵 TO-BE |
| [`workflow-05-fertilizer-followup.mmd`](./to-be/workflow-05-fertilizer-followup.mmd) | State Machine | Persistent fertilizer recommendation and adaptive follow-up state machine with deficiency revision loops. | 🔵 TO-BE |


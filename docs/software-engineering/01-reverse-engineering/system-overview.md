# 02. Current System Overview

## 1. What the System Does
The **Greenfield Agricultural Dispatch System** coordinates daily farm operations, machinery assignments, chemical spraying compliance, and operational contingency rescheduling for the Greenfield Agricultural Agency.

### Core Implemented Capabilities (AS-IS):
- **Autonomous Equipment Dispatching**: Handles single and batch equipment dispatches while validating customer credit, field ownership, machine idle state, and chemical restrictions ([`mcp_server/tools.py:99-234`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L99-L234)).
- **Human-in-the-Loop Sign-off**: Restricts chemical spraying by triggering FastMCP elicitation prompts for human supervisor confirmation before dispatching restricted chemicals ([`mcp_server/tools.py:173-193`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L173-L193)).
- **Knowledge Retrieval (RAG)**: Retrieves SOPs, operating manuals, and chemical safety buffer regulations using hybrid dense vector search combined with BM25 keyword search ([`rag/retrievers.py:24-45`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/retrievers.py#L24-L45)).
- **Self-RAG Grounding Verification**: Evaluates retrieved chunks and generated answers using a structured LLM verification pass ([`rag/verifier.py:25-32`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/verifier.py#L25-L32)).
- **Dual-Layer Memory Management**: Short-term memory with bounded turns and routing of evicted messages to long-term episodic events and semantic facts ([`agent/memory/memory.py:14-120`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/memory/memory.py#L14-L120)).
- **Semantic Memory Consolidation**: LLM-driven consolidation that resolves contradictions, versions facts, and persists to JSON ([`agent/memory/consolidation.py:32-99`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/memory/consolidation.py#L32-L99)).
- **7 Planning & Reasoning Algorithms**:
  1. Static DAG Decomposition (`/plan` or `/dag`)
  2. Dynamic Adaptive Decomposition (`/dynamic`)
  3. Plan-and-Solve (`/ps`)
  4. Tree-of-Thoughts (`/tot`)
  5. Language Agent Tree Search (`/lats`)
  6. Reflexion (`/reflexion`)
  7. Self-Refine (`/refine`)

---

## 2. Who Interacts With It
1. **Primary Actor**: Human Dispatcher / Logistics Coordinator
   - Interacts via the command-line interface in [`main.py:246`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/main.py#L246) or evaluation scripts in [`demo.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/demo.py).
   - Issues natural language requests or slash commands.
2. **Supervisor / Manager**:
   - Responds to FastMCP elicitation requests when restricted chemicals require sign-off ([`mcp_client/client.py:27-48`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_client/client.py#L27-L48)).
3. **External Systems**:
   - **Groq LLM API**: Receives chat completion requests with structured output schemas.
   - **SQLite (`farm.db`)**: Database server embedded directly via Python's standard library.
   - **ChromaDB**: Embedded vector engine running locally on disk.

---

## 3. Main Architectural Components & Communication

```
[ Human Dispatcher ]
       │
       ▼ (CLI Stdio)
┌─────────────────────────────────────────────────────────────┐
│ main.py (REPL & Command Router)                             │
├─────────────────────────────────────────────────────────────┤
│ ├── agent/agent.py (ReAct AgentStep Loop)                   │
│ ├── agent/context.py (Recursive Summarization / Pruning)    │
│ ├── agent/memory/ (ShortTerm, LongTerm, Consolidation)      │
│ └── agent/algorithms/ (7 Planning & Reasoning Algorithms)    │
└─────────────────────────────────────────────────────────────┘
       │
       ▼ (FastMCP Client: JSON-RPC over stdio / http)
┌─────────────────────────────────────────────────────────────┐
│ mcp_server/server.py & tools.py                             │
├─────────────────────────────────────────────────────────────┤
│ ├── Tools: dispatch_equipment, batch_dispatch,              │
│ │          process_payment, log_incident_note,              │
│ │          search_agricultural_knowledge                    │
│ ├── Resources: pesticide-compliance, equipment-status       │
│ └── Prompt: draft_delay_explanation                         │
└─────────────────────────────────────────────────────────────┘
       │                              │
       ▼ (sqlite3 driver)             ▼ (ChromaDB + BM25)
┌───────────────────────────┐  ┌──────────────────────────────┐
│ SQLite DB (db/farm.db)    │  │ ChromaDB (rag/vector_store)  │
│ 7 Relational Tables       │  │ Embeddings: MiniLM-L6-v2     │
└───────────────────────────┘  └──────────────────────────────┘
```

---

## 4. Location of Core Concerns

| Architectural Concern | Implementation Location | Evidence / File Citation |
| :--- | :--- | :--- |
| **LLM Inference** | Initialized via `init_chat_model` | [`agent/agent.py:35-43`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py#L35-L43), [`config.py:1-2`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/config.py#L1-L2) |
| **RAG Knowledge Store** | Local ChromaDB + all-MiniLM-L6-v2 | [`rag/vector_store.py:6-20`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/vector_store.py#L6-L20) |
| **RAG Search Engine** | Hybrid Dense + BM25Okapi | [`rag/retrievers.py:24-45`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/retrievers.py#L24-L45) |
| **Self-RAG Verifier** | Structured output Pydantic verification | [`rag/verifier.py:25-32`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/verifier.py#L25-L32) |
| **MCP Server & Tools** | FastMCP app & decorated tool functions | [`mcp_server/server.py:34-46`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/server.py#L34-L46), [`mcp_server/tools.py:43-234`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L43-L234) |
| **MCP Client Subprocess**| Subprocess stdio transport with handlers | [`mcp_client/client.py:51-108`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_client/client.py#L51-L108) |
| **Domain Safety Checks** | GreenfieldEnvironment domain rules | [`agent/algorithms/environment.py:29-128`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/environment.py#L29-L128) |
| **Relational Data** | SQLite database `farm.db` | [`db/schema.sql:1-193`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/schema.sql#L1-L193), [`db/seed.sql:1-119`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/seed.sql#L1-L119) |
| **Memory Persistence** | JSON file `long_term_memory.json` | [`agent/memory/memory.py:16-59`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/memory/memory.py#L16-L59) |
| **Context Management** | Sliding window, masking, summarization | [`agent/context.py:14-92`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/context.py#L14-L92) |

---

## 5. Architectural Diagram Reference
- Container Overview: [`diagrams/as-is/container.mmd`](../diagrams/as-is/container.mmd)
- Agent Architecture: [`diagrams/as-is/agent-architecture.mmd`](../diagrams/as-is/agent-architecture.mmd)

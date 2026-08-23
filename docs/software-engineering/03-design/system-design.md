# 01. Target System Design (TO-BE)

## 1. Executive Summary & Design Principles
The **Target (TO-BE) System Design** establishes a resilient, secure, and production-ready architecture for the Greenfield Agricultural Dispatch System. It resolves all identified gaps and architectural smells from Phase 2 without unnecessary rewrites, following four core principles:

1. **Grounded Verification First**: Every safety, mechanical, and regulatory constraint must be validated against live relational database state rather than heuristic text pattern matching.
2. **Strict Protocol & Tool Isolation**: FastMCP server operations must be authenticated, schema-validated, and atomically transacted with full audit logging.
3. **Resilient Multi-Provider AI Tier**: LLM routing must support multi-provider fallbacks (Groq primary, Mistral/OpenAI secondary) and structured output guarantees.
4. **Stateful Graph Workflows**: The agent orchestration evolves from a flat turn loop into a LangGraph `StateGraph` with explicit checkpointing, error recovery, and human-in-the-loop nodes.

---

## 2. Target Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│ Client Tier: Web UI (React SPA) & Rich CLI Terminal         │
└──────────────────────────────┬──────────────────────────────┘
                               │ (HTTPS / FastMCP SSE)
┌──────────────────────────────▼──────────────────────────────┐
│ API & Security Gateway (FastAPI Ingress + JWT Auth)         │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
┌──────────────▼──────────────┐┌──────────────▼───────────────┐
│ LangGraph StateGraph Worker ││ FastMCP Enterprise Service   │
│ - Intent Classifier         ││ - RBAC Guard & Pydantic V2   │
│ - Plan Selector (7 Algos)   ││ - Atomic SQL Transactions    │
│ - Live Grounded Validator   ││ - Real-time Progress (SSE)   │
│ - Self-RAG Verifier Gate    ││ - Structured Audit Logger    │
└──────────────┬──────────────┘└──────────────┬───────────────┘
               │                              │
┌──────────────▼──────────────────────────────▼───────────────┐
│ Storage Tier: PostgreSQL (farm_prod), ChromaDB, Redis 7     │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Key Design Decisions

| Decision ID | Decision | Rationale | Alternatives Considered |
| :--- | :--- | :--- | :--- |
| **DEC-01** | Transition from text regex in `GreenfieldEnvironment` to live SQL query checks in `farm.db`. | Prevents hallucinated approvals where the LLM produces valid text but violates real machine/field status. | Mock environment, pure LLM self-evaluation (rejected as ungrounded). |
| **DEC-02** | Evolve ReAct loop to LangGraph `StateGraph` workflow. | Enables conditional branching, deterministic rollback, and native human-in-the-loop checkpoints. | Custom while-loop (current AS-IS, error-prone). |
| **DEC-03** | Persist incident notes to `Incident_Notes` table with foreign key linkage. | Closes critical data loss defect in `log_incident_note`. | File logging, in-memory queue. |
| **DEC-04** | Fix elicitation handler UI string from `"REFUND CONFIRMATION"` to contextual chemical sign-off. | Eliminates confusing UX artifact during restricted chemical dispatch. | Generic yes/no prompt. |
| **DEC-05** | Add Reciprocal Rank Fusion (RRF) and Cross-Encoder reranking to RAG. | Improves precision on complex multi-hop agricultural SOP queries. | Naive dense search only. |

---

## 4. Architectural Diagram Reference
- TO-BE Context Diagram: [`diagrams/to-be/context.mmd`](../diagrams/to-be/context.mmd)
- TO-BE Container Diagram: [`diagrams/to-be/container.mmd`](../diagrams/to-be/container.mmd)

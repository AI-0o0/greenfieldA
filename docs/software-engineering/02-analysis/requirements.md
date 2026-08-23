# 01. Reconstructed System Requirements

This document categorizes all reconstructed requirements based on empirical evidence from the repository, separating directly confirmed behavior from inferred and unknown requirements.

---

## 1. Confirmed Requirements (🟢 CONFIRMED)
Directly observable in source code, schemas, and tests:

1. **REQ-CONF-01 (Single Equipment Dispatch)**: The system must validate customer credit hold, field ownership, equipment idle status, and chemical sign-off requirements before creating a dispatch record in `farm.db` ([`mcp_server/tools.py:99-234`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L99-L234)).
2. **REQ-CONF-02 (Restricted Chemical Sign-off)**: The system must pause dispatch execution and request interactive human sign-off via FastMCP elicitation when `Chemicals.requires_signoff == 1` ([`mcp_server/tools.py:173-193`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L173-L193)).
3. **REQ-CONF-03 (Batch Dispatching)**: The system must support batch dispatch of multiple machines to a single field while emitting sequential progress notifications ([`mcp_server/tools.py:73-91`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L73-L91)).
4. **REQ-CONF-04 (Credit Hold Clearance)**: Processing a customer payment must immediately clear their `credit_hold` in the database and notify connected sessions ([`mcp_server/tools.py:63-71`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L63-L71)).
5. **REQ-CONF-05 (Hybrid Knowledge Retrieval)**: The system must retrieve SOPs and equipment manuals by fusing ChromaDB dense vector similarity and BM25Okapi keyword search ([`rag/retrievers.py:24-45`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/retrievers.py#L24-L45)).
6. **REQ-CONF-06 (Self-RAG Grounding)**: Retrieved context and generated answers must be verified for factual support and query relevance using a structured LLM verifier ([`rag/verifier.py:25-32`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/verifier.py#L25-L32)).
7. **REQ-CONF-07 (7 Planning Algorithms)**: The system must provide direct slash-command execution for Static DAG, Dynamic Decomposition, Plan-and-Solve, Tree-of-Thoughts, LATS, Reflexion, and Self-Refine ([`main.py:68-230`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/main.py#L68-L230)).
8. **REQ-CONF-08 (Dual-Layer Memory)**: Short-term conversational context must evict older turns to long-term episodic events, and a semantic consolidator must extract versioned facts to JSON ([`agent/memory/`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/memory)).

---

## 2. Inferred Requirements (🟡 INFERRED)
Strongly implied by database models, comments, and project design:

1. **REQ-INF-01 (Role-Based Tool Gating)**: Technicians have defined roles (`dispatcher`, `technician`, `manager`) and `authenticated` flags in `Technicians` table, implying intended role-based access control for high-risk operations like `emergency_stop` or dispatch cancellation ([`db/schema.sql:47-53`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/schema.sql#L47-L53)).
2. **REQ-INF-02 (Incident Note Persistence)**: An `Incident_Notes` table exists with severity ratings and resolution flags, implying field incidents should be stored and summarized for maintenance analysis ([`db/schema.sql:134-163`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/db/schema.sql#L134-L163)).
3. **REQ-INF-03 (Web UI Platform)**: The `platform/frontend` directory contains an HTML/JS interface with an agent selector dropdown, implying an intended web dashboard for dispatchers ([`platform/frontend/index.html`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/platform/frontend/index.html)).

---

## 3. Unknown Requirements (🔴 UNKNOWN)
Cannot be determined from available evidence:

1. **REQ-UNK-01 (Multi-User Concurrent Isolation)**: How concurrent dispatchers should be isolated when modifying the single SQLite `farm.db` file.
2. **REQ-UNK-02 (Automated Test Coverage Standards)**: Target code coverage and regression standards (empty `tests/` directory).
3. **REQ-UNK-03 (Production LLM Fallback)**: Behavior when the primary Groq API endpoint encounters rate limits or service outages.

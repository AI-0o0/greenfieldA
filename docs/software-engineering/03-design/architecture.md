# 02. Target Layered Architecture

## 1. Architectural Layers & Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Presentation & Interaction Layer                         │
│    - React Management Dashboard                             │
│    - Dispatcher Rich CLI Terminal (main.py)                 │
├─────────────────────────────────────────────────────────────┤
│ 2. API Gateway & Ingress Layer                              │
│    - FastAPI Gateway with JWT / OAuth2 Auth                 │
│    - Rate Limiting, Request Validation & OpenAPI Docs       │
├─────────────────────────────────────────────────────────────┤
│ 3. Agent & Planning Orchestration Layer                     │
│    - LangGraph StateGraph Engine                            │
│    - 7 Planning Algorithm Engines (DAG, Dynamic, ToT, LATS) │
│    - Dual-Layer Memory & Consolidation Worker               │
├─────────────────────────────────────────────────────────────┤
│ 4. Tool & Protocol Layer                                    │
│    - FastMCP Microservice (stdio & SSE Streamable HTTP)     │
│    - Pydantic V2 Strict Input Validation & RBAC Gates       │
├─────────────────────────────────────────────────────────────┤
│ 5. Knowledge & Retrieval Layer                              │
│    - Multi-Stage RAG Pipeline (Dense + BM25 + Reranker)     │
│    - Self-RAG Grounding & Factual Verification Gate         │
├─────────────────────────────────────────────────────────────┤
│ 6. Persistence & Infrastructure Layer                       │
│    - Relational Store (PostgreSQL / SQLite farm_prod)       │
│    - Vector Store (ChromaDB Collection)                     │
│    - Cache & State (Redis 7)                                │
│    - Structured Audit & Telemetry Store                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Intersystem Communication Protocols
- **Client to Gateway**: HTTPS REST and WebSocket.
- **Gateway to Agent Worker**: Async Python call / Celery task dispatch.
- **Agent to MCP Server**: FastMCP JSON-RPC over Standard I/O (local) or Server-Sent Events (remote).
- **Server to Database**: SQLAlchemy 2.0 connection pool with transactional unit-of-work.
- **Agent to LLM**: HTTPS TLS 1.3 to Groq / Mistral / OpenAI endpoints with client-side exponential backoff.

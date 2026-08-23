# 08. Project Constraints & Boundaries

## 1. Technical Constraints
- **Python Version**: Configured for Python `>=3.14` ([`pyproject.toml:6`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/pyproject.toml#L6)).
- **Database Engine**: Embedded SQLite3 without external database server requirements.
- **LLM Rate Limits**: Groq API free/standard tier rate limits constrain benchmark concurrency and batch sizes.
- **Local Embedding Execution**: Embeddings must run locally using CPU-friendly models (`all-MiniLM-L6-v2`) without requiring dedicated GPU hardware.

---

## 2. Operational & Domain Constraints
- **Regulatory Strictness**: Chemical application rules (SOP-CHEM-4040, 15m canal buffer, 15 km/h wind limits) are legally mandated and cannot be overridden by the LLM without supervisor sign-off.
- **Human-in-the-Loop Mandate**: Restricted chemical dispatches must never be fully autonomous; human sign-off is a hard legal requirement.

---

## 3. Project Scope Boundaries
- **In-Scope**: CLI dispatch agent, 7 planning algorithms, MCP server/tools, RAG knowledge search, memory consolidation, evaluation benchmarks.
- **Out-of-Scope (Current State)**: Multi-tenant SaaS authentication, real-time GPS telemetry hardware tracking, IoT tractor sensors, full production web platform.

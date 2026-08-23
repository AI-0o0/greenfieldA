# 10. Codebase Unknowns & Ambiguities

During reverse engineering of the repository, the following areas could not be conclusively determined from existing code or configuration:

| Category | Unknown Item | Evidence / Context | Impact | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Testing** | Complete absence of automated unit/integration tests | [`tests/`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/tests) contains only an empty `__init__.py`. | Regression risk; verification relies entirely on benchmark scripts (`demo.py`). | 🔴 UNKNOWN |
| **Deployment** | Intended containerization & production environment | [`docker/`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/docker) is completely empty. No `Dockerfile` or `docker-compose.yml` exists. | Production deployment topology cannot be confirmed from repository. | 🔴 UNKNOWN |
| **Platform Integration** | Status and roadmap for Web GUI | [`platform/backend/main.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/platform/backend/main.py) is an echo stub returning `"You sent: <message>"`. It does not connect to the agent or MCP client. | Whether the Web platform is an abandoned experiment or future feature is unknown. | 🔴 UNKNOWN |
| **Authentication** | End-to-end authorization enforcement | `Technicians.authenticated` column exists in `farm.db`, but `agent_step()` and most MCP tools do not authenticate sessions. | Security model in multi-user deployment is undetermined. | 🔴 UNKNOWN |
| **Incident Logging** | Incident note persistence strategy | `log_incident_note` returns a success string without inserting into `Incident_Notes` table. | Missing operational record persistence. | 🔴 UNKNOWN |
| **Secrets Management** | Production secret storage | `.env.example` contains only `GROQ_API_KEY`. No secret manager integration exists. | API key storage in production is undefined. | 🔴 UNKNOWN |

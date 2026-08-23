# 04. Non-Functional Requirements (NFR) Analysis

Evidence-based assessment of observable system quality attributes:

---

## 1. Performance & Latency
- **Sub-task Latencies** ([`demo.py:408-437`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/demo.py#L408-L437)):
  - Plan-and-Solve: ~0.9s average latency (1 LLM call).
  - Tree-of-Thoughts: ~3.8s average latency (9 LLM calls).
  - Grounded LATS: ~6.9s average latency (13 LLM calls).
- **Batch Dispatch Sleep** ([`mcp_server/tools.py:82`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L82)):
  - Hardcoded `await asyncio.sleep(0.2)` delay per equipment item in batch dispatch.
- **Vector Search Latency**:
  - Local in-memory ChromaDB search with `all-MiniLM-L6-v2` executes in < 50ms for small corpora.

---

## 2. Reliability & Availability
- **LLM Max Retries** ([`agent/agent.py:42`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py#L42)):
  - Chat models configured with `max_retries = 3` to handle transient network/provider errors.
- **DAG Cycle Detection** ([`agent/algorithms/models.py:33-37`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/models.py#L33-L37)):
  - Graph model enforces DAG acyclicity using NetworkX `is_directed_acyclic_graph()` at model validation time, preventing infinite loop deadlocks during execution.
- **Failover / High Availability**: 🔴 UNKNOWN (Single SQLite database file and single LLM API key; no multi-region redundancy).

---

## 3. Security & Safety
- **Schema Strictness** ([`schemas/tool_inputs.py:20-21`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/schemas/tool_inputs.py#L20-L21)):
  - All tool input models use `ConfigDict(extra="forbid")` to prevent argument injection.
- **Elicitation Guard** ([`mcp_server/tools.py:118-122`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L118-L122)):
  - Strictly disables `dispatch_equipment` if the connected client does not declare the `elicitation` capability.
- **SQL Injection Risk**:
  - Most queries use parameterized SQL (`?` placeholders).
  - ⚠️ `CREATE TABLE IF NOT EXISTS` is invoked during `get_db_connection()`, introducing redundant DDL overhead.

---

## 4. Maintainability & Code Quality
- **Shared Schema Single Source of Truth**:
  - Shared schemas consolidated into [`schemas/tool_inputs.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/schemas/tool_inputs.py) to prevent model drift between client and server.
- **Technical Debt**:
  - Discrepancy between README documented directory paths and actual disk paths.
  - Empty `tests/` directory; zero automated CI unit tests.

---

## 5. Extensibility
- **Centralized Algorithm Router**:
  - `execute_subtask_with_algorithm()` in [`agent/agent.py:129-186`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py#L129-L186) enables plugging new planning algorithms into the system through unified method strings.
- **FastMCP Tool Architecture**:
  - Adding new tools requires only decorating a Python async function with `@mcp.tool()` and declaring its input schema.

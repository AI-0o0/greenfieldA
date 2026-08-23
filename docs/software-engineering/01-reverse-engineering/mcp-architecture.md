# 07. Model Context Protocol (MCP) Reverse Engineering

## 1. FastMCP Server Configuration
The MCP server is implemented in [`mcp_server/server.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/server.py) using the `FastMCP` framework (`fastmcp>=3.4.6`).

- **Server Name**: `"Greenfield-Dispatch-Server"` ([`mcp_server/server.py:34`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/server.py#L34))
- **Transports Supported**:
  - `stdio` (default for subprocess agent integration)
  - `http` / `streamable-http` (port 8080)

---

## 2. Complete MCP Tool Inventory

| Tool Name | Source File & Function | Input Schema | Output Format | Side Effects / Database Operations | Certainty |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `dispatch_equipment` | [`mcp_server/tools.py:99-234`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L99-L234) | `DispatchEquipmentInput`<br/>(`equipment_id`, `field_id`, `customer_id`, `job_type`, `chemical_id`) | String message with dispatch ID & chemical applied | Inserts record into `Dispatch_Jobs`, updates `Equipment.status = 'dispatched'`, triggers human sign-off if chemical is restricted. | 🟢 CONFIRMED |
| `batch_dispatch` | [`mcp_server/tools.py:73-91`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L73-L91) | `BatchDispatchInput`<br/>(`equipment_ids`, `field_id`) | String confirmation message | Iterates through IDs, updates `Equipment.status = 'dispatched'`, sends progress notifications via MCP context. | 🟢 CONFIRMED |
| `process_payment` | [`mcp_server/tools.py:63-71`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L63-L71) | `PaymentInput`<br/>(`customer_id`) | String confirmation message | Updates `Customers.credit_hold = 0`, calls `ctx.session.send_tool_list_changed()`. | 🟢 CONFIRMED |
| `log_incident_note` | [`mcp_server/tools.py:93-96`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L93-L96) | `IncidentInput`<br/>(`raw_note`) | String confirmation message | ⚠️ None. Note is not inserted into `Incident_Notes` table. | 🟢 CONFIRMED |
| `search_agricultural_knowledge`| [`mcp_server/tools.py:43-61`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L43-L61) | `KnowledgeSearchInput`<br/>(`query`) | Formatted document chunks or Self-RAG flag | Queries ChromaDB & BM25Okapi, runs Self-RAG verification. | 🟢 CONFIRMED |

---

## 3. MCP Resources & Prompts

### Resources Exposed ([`mcp_server/server.py:81-119`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/server.py#L81-L119))
1. **`policy://pesticide-compliance`**: Returns read-only policy text (`PESTICIDE_COMPLIANCE_POLICY`) specifying buffer zones (15m canal, 8m controlled, 50m organic), wind limits (15 km/h), sign-off rules, and record-keeping.
2. **`fleet://equipment-status`**: Dynamically queries `Equipment` table and returns a formatted ASCII table of all machines, serial numbers, statuses, and locations.

### Prompts Exposed ([`mcp_server/server.py:124-163`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/server.py#L124-L163))
1. **`draft_delay_explanation(dispatch_id: int)`**: Queries `Dispatch_Jobs`, `Fields`, and `Customers` to format a structured customer delay apology prompt under 80 words.

---

## 4. MCP Protocol Features Utilized
- **Elicitation (Human-in-the-Loop)**: `ctx.elicit()` prompts the user during `dispatch_equipment` if `Chemicals.requires_signoff == 1` ([`mcp_server/tools.py:173`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L173)).
- **Progress Notifications**: `ctx.session.send_progress()` sends real-time batch dispatch completion ratios ([`mcp_server/tools.py:85`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L85)).
- **Dynamic Tool List Notifications**: `ctx.session.send_tool_list_changed()` notifies client when payments clear holds ([`mcp_server/tools.py:70`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L70)).

---

## 5. Architectural Diagram Reference
- MCP Architecture: [`diagrams/as-is/mcp-architecture.mmd`](../diagrams/as-is/mcp-architecture.mmd)
- MCP Tool Interaction Sequence: [`diagrams/as-is/tool-interaction.mmd`](../diagrams/as-is/tool-interaction.mmd)

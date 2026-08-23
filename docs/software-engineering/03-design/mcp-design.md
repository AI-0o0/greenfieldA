# 06. Target Model Context Protocol (MCP) Design

## 1. Tool Boundary Cleanup & Enhancements
1. **`dispatch_equipment`**:
   - Wrap in atomic transaction with `conn.rollback()` on validation error.
   - Enforce customer and field existence.
2. **`log_incident_note` (Fixed)**:
   - Insert raw note, equipment ID, technician ID, severity, and timestamp into `Incident_Notes` table.
   - Return structured confirmation with created `incident_id`.
3. **`emergency_stop` (New Tool)**:
   - Immediately sets all machines on a field to `status = 'offline'`.
   - Inserts critical incident record into `Incident_Notes`.
   - Requires `Technicians.role IN ('dispatcher', 'manager')`.

---

## 2. FastMCP Context & Protocol Refinements
- **Contextual Elicitation Prompts**:
  - Replace refund message with chemical sign-off template displaying Chemical Name, Field Name, Customer Company, and specific regulatory warnings.
- **Dynamic Resource Subscriptions**:
  - Expose `fleet://equipment-status` and `weather://field-forecast` with SSE updates.

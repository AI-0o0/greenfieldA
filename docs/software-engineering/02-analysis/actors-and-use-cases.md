# 02. Actors and Use Cases

## 1. System Actors

| Actor | Type | Description |
| :--- | :--- | :--- |
| **Human Dispatcher** | Primary Human Actor | Logistics technician who interacts with the CLI / Web UI to schedule jobs, run planning algorithms, and monitor fleet status. |
| **Field Supervisor / Manager** | Secondary Human Actor | Operations lead who reviews and approves high-risk or restricted chemical dispatch requests via FastMCP elicitation. |
| **Farm Customer** | Indirect Stakeholder | Customer whose fields are serviced and who must clear credit holds to receive service. |
| **Groq Cloud LLM API** | External System Actor | Provides fast inference (`openai/gpt-oss-120b`) for planning, reflection, memory extraction, and tool selection. |
| **SQLite Database (`farm.db`)** | Internal System Actor | Manages transactional data persistence and state verification. |
| **ChromaDB Vector Store** | Internal System Actor | Provides dense vector retrieval for agricultural manuals and SOPs. |

---

## 2. Reconstructed Use Cases

```
  ┌─────────────────────────────────────────────────────────────┐
  │ Human Dispatcher                                            │
  │   ├── [UC-01] Dispatch Single Equipment                     │
  │   ├── [UC-02] Batch Dispatch Equipment                      │
  │   ├── [UC-03] Process Payment & Clear Credit Hold           │
  │   ├── [UC-04] Log Operational Incident Note                 │
  │   ├── [UC-05] Search Agricultural Knowledge (RAG)           │
  │   ├── [UC-07] Reshuffle Schedule via Static DAG (/plan)     │
  │   ├── [UC-08] Reshuffle Schedule via Dynamic Loop (/dynamic)│
  │   ├── [UC-09] Prioritize Fields via ToT / PS (/tot, /ps)    │
  │   └── [UC-10] Run Self-Correction Search (LATS / Reflexion) │
  └─────────────────────────────────────────────────────────────┘
  ┌─────────────────────────────────────────────────────────────┐
  │ Field Supervisor                                            │
  │   └── [UC-06] Approve Restricted Chemical Sign-off (Elicit) │
  └─────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Use Case Specifications

### UC-01: Dispatch Single Equipment
- **Primary Actor**: Human Dispatcher
- **Preconditions**: Equipment is `idle`, customer has no credit hold, field is owned by customer.
- **Main Success Scenario**:
  1. Dispatcher specifies equipment ID, field ID, job type, and customer ID.
  2. System verifies all database constraints.
  3. System inserts record into `Dispatch_Jobs` and sets `Equipment.status = 'dispatched'`.
  4. System returns confirmation with dispatch ID.
- **Extensions**: If chemical requires sign-off, system triggers UC-06 before proceeding.

### UC-06: Approve Restricted Chemical Dispatch (Sign-off)
- **Primary Actor**: Field Supervisor
- **Preconditions**: `dispatch_equipment` was invoked with a chemical where `requires_signoff == 1`.
- **Main Success Scenario**:
  1. FastMCP server pauses execution and issues `ctx.elicit()` prompt.
  2. Supervisor enters `confirm`.
  3. System sets `approval_status = 'approved'` and completes the dispatch.
- **Alternative Flow (Decline)**: Supervisor enters `cancel`; dispatch is aborted with an error message.

---

## 4. Architectural Diagram Reference
- Reconstructed Use Case Diagram: [`diagrams/as-is/use-case.mmd`](../diagrams/as-is/use-case.mmd)

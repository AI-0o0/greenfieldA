# 03. Target Component Design

## 1. Agent Subsystem Components
- **`IntentClassifierNode`**: Classifies inbound requests into routine tool calls, planning slash commands, policy lookups, or emergency stops.
- **`PlanningRouterNode`**: Routes complex tasks to the optimal algorithm based on benchmark characteristics:
  - Linear math / dosages -> `Plan-and-Solve`
  - Combinatorial field sequencing -> `Tree-of-Thoughts`
  - High-stakes multi-constraint reshuffling -> `Grounded LATS`
  - Work order drafting & summaries -> `Self-Refine`
- **`GroundedValidatorNode`**: Executes direct SQL verification queries against `farm.db` before and after plan formulation.
- **`HumanInTheLoopNode`**: Suspends graph execution and awaits external webhook or CLI input for restricted chemical approvals.

---

## 2. MCP Subsystem Components
- **`RBACPolicyGuard`**: Inspects caller session token against `Technicians.role` before invoking sensitive tools (e.g. `emergency_stop`, `process_payment`).
- **`AtomicDispatchTool`**: Executes dispatch creation, equipment status update, and audit log generation inside a single ACID database transaction.
- **`PersistentIncidentTool`**: Inserts structured incident notes into `Incident_Notes` with automatic severity classification and machine linkage.

---

## 3. Architectural Diagram Reference
- TO-BE Component Diagram (Agent): [`diagrams/to-be/component-agent.mmd`](../diagrams/to-be/component-agent.mmd)
- TO-BE Component Diagram (MCP): [`diagrams/to-be/component-mcp.mmd`](../diagrams/to-be/component-mcp.mmd)

# 09. AS-IS Primary System Workflows

## Workflow 1: Single Equipment Dispatch with Elicitation Sign-Off
- **Trigger**: User requests equipment dispatch for restricted spraying (e.g. "Dispatch SPR-3001 to Field 2 for Glyphosate").
- **Actor**: Human Dispatcher / Operations Manager.
- **Preconditions**:
  - Customer exists and `credit_hold == 0`.
  - Target field is owned by requesting customer.
  - Equipment is in `status = 'idle'`.
  - Chemical exists; if `requires_signoff == 1`, supervisor must approve.
- **Main Sequence**:
  1. Agent parses intent and issues `dispatch_equipment` action.
  2. MCP server validates payload via Pydantic & JSON-Schema.
  3. MCP server queries `Customers`, `Fields`, `Equipment`, and `Chemicals`.
  4. Server identifies `Chemicals.requires_signoff == 1` and triggers `ctx.elicit()`.
  5. FastMCP client displays prompt to dispatcher.
  6. Dispatcher enters `confirm`.
  7. Server records `INSERT INTO Dispatch_Jobs` and updates `Equipment.status = 'dispatched'`.
  8. Agent generates final confirmation answer.
- **Side Effects**: `farm.db` updated; equipment status changed to `dispatched`.
- **Mermaid Diagram**: [`diagrams/as-is/workflow-01.mmd`](../diagrams/as-is/workflow-01.mmd)

---

## Workflow 2: Operational Reshuffle via Static DAG / Dynamic Decomposition
- **Trigger**: Operational disruption occurs (e.g. machinery breakdown, wind advisory > 15 km/h).
- **Actor**: Logistics Dispatcher.
- **Preconditions**: Disruption goal clearly specified.
- **Main Sequence**:
  1. Dispatcher executes `/plan <goal>` or `/dynamic <goal>`.
  2. Decomposition engine calls Groq LLM to generate task DAG or dynamic next steps.
  3. Graph validation verifies acyclicity with NetworkX.
  4. Node tasks execute in topological parallel batches using `ThreadPoolExecutor`.
  5. Terminal synthesis node aggregates results into a final schedule.
- **Side Effects**: Output displayed to console; evaluation traces logged to `evaluation/results/`.
- **Mermaid Diagram**: [`diagrams/as-is/workflow-02.mmd`](../diagrams/as-is/workflow-02.mmd)

---

## Workflow 3: Agricultural Knowledge Search (Hybrid RAG + Self-RAG)
- **Trigger**: User asks policy question (e.g. "What is the canal buffer distance for SPR-3001?").
- **Actor**: Dispatcher / Support Agent.
- **Preconditions**: ChromaDB collection initialized.
- **Main Sequence**:
  1. Agent invokes `search_agricultural_knowledge(query)`.
  2. Tool executes `hybrid_search()` running dense vector search + BM25Okapi keyword search.
  3. Chunks are merged and deduplicated.
  4. `self_rag_verify()` validates relevance and grounding via structured LLM call.
  5. Grounded knowledge returned to agent to formulate final answer.
- **Side Effects**: None (read-only query).
- **Mermaid Diagram**: [`diagrams/as-is/workflow-03.mmd`](../diagrams/as-is/workflow-03.mmd)

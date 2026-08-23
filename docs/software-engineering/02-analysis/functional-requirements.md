# 03. Functional Requirements Specification

Each requirement is formally reconstructed from implemented code evidence:

---

### FR-001: Schema-Level Dispatch Validation
- **Description**: The system must enforce strict schema validation on all equipment dispatch arguments before database operations.
- **Actor**: Dispatcher
- **Preconditions**: JSON/dict arguments provided.
- **Main Flow**:
  1. Validate payload against Pydantic `DispatchEquipmentInput` and `DISPATCH_SCHEMA`.
  2. Reject extra parameters (`extra='forbid'`).
- **Evidence**: [`mcp_server/tools.py:103-107`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L103-L107), [`schemas/tool_inputs.py:50-55, 89-100`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/schemas/tool_inputs.py#L50-L55)
- **Confidence**: 🟢 CONFIRMED

---

### FR-002: Customer Credit Hold Enforcement
- **Description**: Equipment dispatch requests for customers with an active credit hold (`credit_hold = 1`) must be blocked.
- **Actor**: Dispatcher
- **Preconditions**: Dispatch request issued.
- **Main Flow**:
  1. Query `Customers` table for `customer_id`.
  2. Verify `credit_hold == 0`.
  3. Abort with security error if credit hold is active.
- **Evidence**: [`mcp_server/tools.py:132-136`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L132-L136), [`agent/algorithms/environment.py:105-112`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/environment.py#L105-L112)
- **Confidence**: 🟢 CONFIRMED

---

### FR-003: Cross-Customer Field Authorization
- **Description**: Dispatching equipment to a field that is not owned by the requesting customer must be blocked.
- **Actor**: Dispatcher
- **Preconditions**: Dispatch request issued.
- **Main Flow**:
  1. Query `Fields` table for `field_id`.
  2. Verify `Fields.customer_id == requesting customer_id`.
  3. Raise ValueError if ownership mismatch occurs.
- **Evidence**: [`mcp_server/tools.py:144-150`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L144-L150)
- **Confidence**: 🟢 CONFIRMED

---

### FR-004: Equipment Idle Status Verification
- **Description**: Only machinery currently in `status = 'idle'` may be dispatched.
- **Actor**: Dispatcher
- **Preconditions**: Equipment ID supplied.
- **Main Flow**:
  1. Query `Equipment` table.
  2. If `status != 'idle'`, raise ValueError with current machine status.
- **Evidence**: [`mcp_server/tools.py:158-161`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L158-L161)
- **Confidence**: 🟢 CONFIRMED

---

### FR-005: Restricted Chemical Elicitation Sign-off
- **Description**: Spray dispatches involving restricted chemicals must pause for interactive human approval.
- **Actor**: Supervisor / Manager
- **Preconditions**: `job_type = 'spray'` and `Chemicals.requires_signoff == 1`.
- **Main Flow**:
  1. Check client capability for elicitation.
  2. Prompt human via `ctx.elicit()` with chemical danger warning.
  3. Proceed only if `SignoffResponse.approved == True`.
- **Evidence**: [`mcp_server/tools.py:164-193`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L164-L193)
- **Confidence**: 🟢 CONFIRMED

---

### FR-006: Batch Dispatch with Progress Tracking
- **Description**: The system must batch-dispatch multiple machines sequentially and emit progress updates.
- **Actor**: Dispatcher
- **Preconditions**: List of equipment IDs provided.
- **Main Flow**:
  1. Update each equipment ID to `status = 'dispatched'`.
  2. Send progress notifications via `ctx.session.send_progress()`.
- **Evidence**: [`mcp_server/tools.py:73-91`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L73-L91)
- **Confidence**: 🟢 CONFIRMED

---

### FR-007: Payment Processing & Tool List Notification
- **Description**: Customer payment processing must clear credit holds and notify sessions that tool capabilities have changed.
- **Actor**: Dispatcher
- **Preconditions**: Valid customer ID provided.
- **Main Flow**:
  1. Execute `UPDATE CUSTOMERS SET credit_hold = 0 WHERE customer_id = ?`.
  2. Call `ctx.session.send_tool_list_changed()`.
- **Evidence**: [`mcp_server/tools.py:63-71`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_server/tools.py#L63-L71)
- **Confidence**: 🟢 CONFIRMED

---

### FR-008: Hybrid Knowledge Retrieval & Self-RAG
- **Description**: Knowledge searches must combine dense vector retrieval with BM25 keyword matching and Self-RAG verification.
- **Actor**: Dispatcher / Agent
- **Preconditions**: Query string provided.
- **Main Flow**:
  1. Execute `hybrid_search(query, top_k=3)`.
  2. Run `self_rag_verify()` on retrieved chunks.
  3. Return verified chunks or flag relevance failure.
- **Evidence**: [`rag/retrievers.py:24-45`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/retrievers.py#L24-L45), [`rag/verifier.py:25-32`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/rag/verifier.py#L25-L32)
- **Confidence**: 🟢 CONFIRMED

---

### FR-009: Static DAG Task Decomposition & Parallel Execution
- **Description**: Complex goals must be decomposed into a validated directed acyclic graph and executed in parallel topological batches.
- **Actor**: Dispatcher
- **Preconditions**: User issues `/plan <goal>` command.
- **Main Flow**:
  1. Decompose goal with structured `GeneratedPlan` schema.
  2. Validate DAG acyclicity with NetworkX.
  3. Execute independent batches with `ThreadPoolExecutor(max_workers=4)`.
  4. Synthesize final output from terminal node.
- **Evidence**: [`agent/algorithms/decomposition.py:39-95`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/decomposition.py#L39-L95), [`agent/algorithms/models.py:15-63`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/models.py#L15-L63)
- **Confidence**: 🟢 CONFIRMED

---

### FR-010: Dynamic Adaptive Decomposition
- **Description**: The system must support step-by-step dynamic planning that decides the next sub-task conditionally from prior observations.
- **Actor**: Dispatcher
- **Preconditions**: User issues `/dynamic <goal>` command.
- **Main Flow**:
  1. Present prior observations to LLM.
  2. Decide single next task or mark `done = true`.
  3. Execute task and append result to history (up to `max_steps=4`).
- **Evidence**: [`agent/algorithms/dynamic_decomposition.py:12-42`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/dynamic_decomposition.py#L12-L42)
- **Confidence**: 🟢 CONFIRMED

---

### FR-011: Tree-of-Thoughts Combinatorial Ranking
- **Description**: Candidate solutions must be explored across multiple reasoning paths using beam search with structured scoring.
- **Actor**: Dispatcher
- **Preconditions**: User issues `/tot <problem>` command.
- **Main Flow**:
  1. Generate distinct continuations per beam frontier.
  2. Score each candidate with `ThoughtEvaluation` schema.
  3. Prune to top `beam_width` thoughts up to specified depth.
- **Evidence**: [`agent/algorithms/tree_of_thought.py:21-57`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/tree_of_thought.py#L21-L57)
- **Confidence**: 🟢 CONFIRMED

---

### FR-012: Grounded Language Agent Tree Search (LATS)
- **Description**: Candidate dispatch solutions must be searched via MCTS guided by external domain feedback and value estimation.
- **Actor**: Dispatcher
- **Preconditions**: User issues `/lats <task>` command.
- **Main Flow**:
  1. Select leaf using Upper Confidence Bound for Trees (UCT).
  2. Expand `n_actions` candidate states.
  3. Evaluate candidate with `GreenfieldEnvironment`.
  4. Backpropagate combined value (0.75 external + 0.25 model score).
  5. Accumulate episodic reflections on failed branches.
- **Evidence**: [`agent/algorithms/lats.py:92-207`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/lats.py#L92-L207)
- **Confidence**: 🟢 CONFIRMED

---

### FR-013: Reflexion Multi-Trial Self-Correction
- **Description**: When an initial dispatch plan fails domain rules, the agent must generate verbal reflections and retry in a multi-trial loop.
- **Actor**: Dispatcher
- **Preconditions**: User issues `/reflexion <task>` command.
- **Main Flow**:
  1. Execute task with remembered lessons from past trials.
  2. Evaluate trial with `GreenfieldEnvironment`.
  3. If failed, generate first-person reflection and append to memory buffer (up to 3 trials).
- **Evidence**: [`agent/algorithms/reflexion.py:24-77`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/reflexion.py#L24-L77)
- **Confidence**: 🟢 CONFIRMED

---

### FR-014: Self-Refine Deterministic Checks & Critic
- **Description**: Work orders and deliverables must be critiqued against deterministic checks and an independent LLM rubric.
- **Actor**: Dispatcher
- **Preconditions**: User issues `/refine <goal>` command.
- **Main Flow**:
  1. Run `deterministic_checks()` (word count >= 80, goal terms present, structured headings/lists).
  2. Generate rubric critique with separate LLM invocation.
  3. Revise deliverable incorporating both feedback signals.
- **Evidence**: [`agent/algorithms/self_refine.py:7-64`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/self_refine.py#L7-L64)
- **Confidence**: 🟢 CONFIRMED

---

### FR-015: Episodic Memory Eviction & Semantic Consolidation
- **Description**: Evicted short-term messages must be classified and consolidated into versioned semantic facts.
- **Actor**: System (Automatic)
- **Preconditions**: Short-term turns exceed `max_turns=2`.
- **Main Flow**:
  1. Evaluate evicted messages via `decide_memory_fate()`.
  2. Route non-routine facts to `LongTermMemory.episodic_events`.
  3. `SemanticConsolidator` runs consolidation pass, resolves contradictions, and updates `long_term_memory.json`.
- **Evidence**: [`agent/memory/memory.py:88-118`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/memory/memory.py#L88-L118), [`agent/memory/consolidation.py:42-99`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/memory/consolidation.py#L42-L99)
- **Confidence**: 🟢 CONFIRMED

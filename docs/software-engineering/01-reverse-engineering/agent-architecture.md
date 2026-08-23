# 06. Agent Architecture & Reasoning Algorithms

## 1. Agent Architecture & Loop Overview
The agent subsystem in `agent/agent.py` implements a constrained ReAct pattern with structured output enforcement and scratchpad planning integration.

### Core Reasoning Cycle:
1. **Goal Ingestion & Decomposition**: User input is added to `ShortTermMemory`. If no plan exists in the scratchpad, `initialize_plan()` creates a DAG plan.
2. **System Prompt Assembly** ([`agent/agent.py:205-245`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py#L205-L245)): Injects scratchpad plan, active sub-goal, verified semantic facts, recent episodic events, and tool descriptions.
3. **Bounded ReAct Loop** ([`agent/agent.py:302-348`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py#L302-L348)): Loops for up to `MAX_STEPS = 6`. Each step invokes LLM with dynamic `AgentStep` schema.
4. **Action Execution & Self-RAG Verification**: Executes MCP tools or verifies terminal output grounding.

---

## 2. Inventory of the 7 Planning & Reasoning Algorithms

| Algorithm | Implementation File | Key Mechanism & Behavior | Use Case in Greenfield |
| :--- | :--- | :--- | :--- |
| **1. Static DAG Decomposition** | [`agent/algorithms/decomposition.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/decomposition.py) | Generates upfront acyclic dependency graph, validates DAG acyclicity with NetworkX, executes independent nodes in parallel batches using `ThreadPoolExecutor`. | Routine multi-step jobs with clear task boundaries. |
| **2. Dynamic Adaptive Decomposition** | [`agent/algorithms/dynamic_decomposition.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/dynamic_decomposition.py) | Adaptive loop where the LLM decides the next sub-task conditionally based on intermediate execution observations. | Reshuffling under operational shocks when future steps depend on live DB queries. |
| **3. Plan-and-Solve (PS)** | [`agent/algorithms/plan_and_solve.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/plan_and_solve.py) | Zero-shot prompt separating plan derivation from step-by-step mathematical/linear solution execution. | Linear acreage calculations, chemical mixing ratios, fuel math. |
| **4. Tree-of-Thoughts (ToT)** | [`agent/algorithms/tree_of_thought.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/tree_of_thought.py) | Multi-branch beam search (depth=2, beam_width=2) exploring candidate solution states with structured scoring. | Prioritizing and sequencing competing fields under constrained technician capacity. |
| **5. Language Agent Tree Search (LATS)** | [`agent/algorithms/lats.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/lats.py) | Full Monte Carlo Tree Search (Select, Expand, Simulate, Reflect, Backpropagate) combining model value judgments with environment scores. | High-stakes final dispatch proposals under complex multi-resource constraints. |
| **6. Reflexion** | [`agent/algorithms/reflexion.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/reflexion.py) | Multi-trial trial loop (up to 3 trials) carrying verbal self-reflections in an episodic memory buffer across attempts. | Constraint satisfaction problems where trial failure details guide the next attempt. |
| **7. Self-Refine** | [`agent/algorithms/self_refine.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/self_refine.py) | Single-pass drafting, deterministic rule checks, and independent rubric critic pass. | Formatting technician work orders, incident summaries, and customer delay notices. |

---

## 3. Environment & Validation Subsystem
The project contains two environment classes in [`agent/algorithms/environment.py`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/algorithms/environment.py):
1. **`Environment`**: Base class supporting stochastic simulation (Beta distribution scoring).
2. **`GreenfieldEnvironment`**: Evaluates 10 domain rules (canal buffer, organic drift, wind threshold, heat window, soil moisture, calibration, SOP sign-off, credit hold, allergy contamination, and length sanity check).

> [!WARNING]
> **Implementation vs Documentation Reality**: `GreenfieldEnvironment._check_agricultural_constraints()` evaluates candidate plans using **string keyword and substring matching** on the candidate text, rather than executing live SQL queries against `farm.db`.

---

## 4. Memory Architecture & Consolidation
- **ShortTermMemory** ([`agent/memory/memory.py:61-120`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/memory/memory.py#L61-L120)):
  - Manages active conversation turns (`max_turns=2` in `main.py`).
  - When turns exceed `max_turns`, older messages are evaluated by `decide_memory_fate()`.
  - Eligible messages are routed to `LongTermMemory.episodic_events`.
- **SemanticConsolidator** ([`agent/memory/consolidation.py:32-99`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/memory/consolidation.py#L32-L99)):
  - Batch consolidates unprocessed episodic events.
  - Generates structured `FactUpdate` models.
  - Updates `long_term_memory.json` with version tracking, conflict resolution (`resolution_type = 'resolve_contradiction'`), and timestamped history.

---

## 5. Architectural Diagram Reference
- Agent Architecture: [`diagrams/as-is/agent-architecture.mmd`](../diagrams/as-is/agent-architecture.mmd)
- Agent Step Loop Sequence: [`diagrams/as-is/agent-sequence.mmd`](../diagrams/as-is/agent-sequence.mmd)

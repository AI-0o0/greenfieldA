# 04. Execution Flow Analysis

## 1. Complete Startup Sequence
Tracing the exact initialization flow from `main.py` entry point:

1. **Module Imports & Memory Instantiation** ([`main.py:10-24`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/main.py#L10-L24)):
   - `LongTermMemory` initializes and reads `long_term_memory.json` if it exists.
   - `ShortTermMemory` is constructed with `max_turns=2` and linked to `long_term`.
   - `SemanticConsolidator` is instantiated with the `long_term` instance.
2. **Subprocess Client Creation** ([`main.py:234`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/main.py#L234)):
   - `create_client(mode="stdio")` is entered as an async context manager.
   - `mcp_client/client.py:53-61` launches `python mcp_server/server.py stdio` as a subprocess via standard I/O pipes.
3. **Capabilities Discovery & Pre-warming** ([`main.py:236`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/main.py#L236), [`mcp_client/client.py:82-106`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/mcp_client/client.py#L82-L106)):
   - Client queries `list_resources()`, `list_prompts()`, and `list_tools()`.
   - Discovers the 5 exposed MCP tools: `dispatch_equipment`, `batch_dispatch`, `process_payment`, `log_incident_note`, `search_agricultural_knowledge`.
4. **Interactive REPL Loop** ([`main.py:244-293`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/main.py#L244-L293)):
   - Prompts the user with `User: ` asynchronously.
   - Evaluates input for slash commands or standard agent dialogue.

---

## 2. Request Handling & Command Routing
When user input is received in [`main.py:260`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/main.py#L260):

### Path A: Direct Algorithm Slash Commands ([`main.py:68-230`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/main.py#L68-L230))
If the command starts with a slash command, execution bypasses the ReAct agent loop and directly executes the requested planning algorithm via `execute_subtask_with_algorithm()`:
- `/plan <goal>` or `/dag <goal>`: Calls `decompose_goal()` → DAG validation → topological `ThreadPoolExecutor` batch execution → `final_output()` synthesis.
- `/dynamic <goal>`: Calls `dynamic_decomposition()` in an adaptive loop (up to 4 steps).
- `/ps <question>`: Calls `plan_and_solve()` zero-shot 2-stage prompt.
- `/tot <problem>`: Calls `tree_of_thoughts()` beam search (depth=2, beam_width=2).
- `/lats <task>`: Calls `lats()` Monte Carlo tree search with `GreenfieldEnvironment`.
- `/reflexion <task>`: Calls `reflexion()` multi-trial loop (max_trials=3).
- `/refine <goal>`: Calls `reflect_and_refine()` with deterministic checks + critic.

### Path B: Full Autonomous Support Agent Step ([`main.py:265-270`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/main.py#L265-L270))
Calls `agent_step(client, memory, user_input)`:
1. Adds user message to `ShortTermMemory` ([`agent/agent.py:366`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py#L366)).
2. If scratchpad plan is empty, initializes DAG decomposition via `initialize_plan()` ([`agent/agent.py:370`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py#L370)).
3. Discovers available tools dynamically ([`agent/agent.py:372`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py#L372)).
4. Runs Self-RAG verification on active long-term memory facts ([`agent/agent.py:221`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py#L221)).
5. Assembles system prompt combining plan scratchpad, semantic facts, episodic events, and tool instructions ([`agent/agent.py:205-245`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py#L205-L245)).
6. Runs `execute_step_loop()` for up to `MAX_STEPS = 6` iterations ([`agent/agent.py:302-348`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py#L302-L348)).

---

## 3. ReAct Step Execution Loop
Inside `execute_step_loop()` ([`agent/agent.py:317-348`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py#L317-L348)):

1. **Context Pruning**: Calls `recursive_summarization(raw_context, model, keep_recent=6)` to compact messages older than 6 turns ([`agent/context.py:39-58`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/context.py#L39-L58)).
2. **Structured LLM Generation**: Invokes `model.ainvoke(pruned_context)` where the model is constrained via Pydantic schema `AgentStep` with `action: Literal[...]` dynamically generated from available tools ([`agent/schema.py:51-69`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/schema.py#L51-L69)).
3. **Step Handling** ([`agent/agent.py:247-300`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py#L247-L300)):
   - If `step.plan_updated`: Updates scratchpad `plan` and `current_subgoal`.
   - If `step.action in TERMINAL_ACTIONS` (`final_answer`, `end_conversation`, `escalate`):
     - Executes Self-RAG verification on the final answer ([`agent/agent.py:276`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/agent/agent.py#L276)).
     - Returns step to terminate loop.
   - If `step.action` is a tool:
     - Validates input schema against `ACTION_INPUT_SCHEMAS` ([`schemas/tool_inputs.py:107-125`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/schemas/tool_inputs.py#L107-L125)).
     - Invokes `client.call_tool(step.action, {"input_data": payload})` over JSON-RPC.
     - Receives tool observation and appends `[Observation]: <result>` to short-term memory.
     - Continues to next step iteration.

---

## 4. Post-Step Semantic Consolidation
After each user turn completes ([`main.py:288`](file:///D:/courses/Autonomous%20Agents/Week%203/greenfield-mcp-dispatch/main.py#L288)):
- `consolidator.run_consolidation_pass()` examines all unconsolidated episodic events.
- Extracts persistent facts, resolves contradictions against active facts, increments version counters, and writes back to `long_term_memory.json`.

---

## 5. Architectural Diagram Reference
- Main Execution Sequence: [`diagrams/as-is/main-execution-flow.mmd`](../diagrams/as-is/main-execution-flow.mmd)
- Agent Step Loop Sequence: [`diagrams/as-is/agent-execution-flow.mmd`](../diagrams/as-is/agent-execution-flow.mmd)

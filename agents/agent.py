from .algorithms.plan_and_solve import plan_and_solve
from .algorithms.tree_of_thought import tree_of_thoughts
from .algorithms.lats import lats
from .algorithms.reflexion import reflexion
from .algorithms.self_refine import reflect_and_refine
from .algorithms.environment import Environment, GreenfieldEnvironment

from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from pydantic import ValidationError
from langchain_core.messages import HumanMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain.chat_models import init_chat_model

from rag.verifier import self_rag_verify
from .memory.memory import ShortTermMemory
from .context import recursive_summarization
from .algorithms.decomposition import decompose_goal, execute_plan, final_output
from .algorithms.dynamic_decomposition import dynamic_decomposition
from .algorithms.models import Plan

from config import MODEL_NAME, MODEL_PROVIDER
from .schema import (
    ACTION_INPUT_SCHEMAS,
    AgentStep,
    build_agent_step_model,
    TERMINAL_ACTIONS,
    MAX_STEPS,
    build_system_prompt
)

load_dotenv()


def get_base_llm() -> BaseChatModel:
    """Returns the default BaseChatModel for decomposition and planning tasks."""
    return init_chat_model(
        model=MODEL_NAME,
        model_provider=MODEL_PROVIDER,
        max_tokens=1024,
        temperature=0.1,
        max_retries=3,
    )


def initialize_plan(
    goal: str,
    memory: ShortTermMemory,
    llm: Optional[BaseChatModel] = None,
    dynamic: bool = False,
) -> Optional[Plan]:
    """
    Decomposes a user goal using static DAG decomposition (or dynamic decomposition)
    and initializes the planning scratchpad with the current plan and active subgoal.
    """
    base_llm = llm or get_base_llm()
    try:
        if dynamic:
            history = dynamic_decomposition(goal=goal, llm=base_llm, max_steps=4)
            if history:
                tasks_summary = "\n".join(f"- {task}: {result}" for task, result in history)
                memory.scratchpad["plan"] = tasks_summary
                memory.scratchpad["current_subgoal"] = history[-1][0] if history else None
                memory.scratchpad["dynamic_history"] = history
            return None
        else:
            plan = decompose_goal(goal=goal, llm=base_llm)
            ordered_tasks = plan.topological_order()
            tasks_repr = "\n".join(
                f"[{t.id}] {t.instruction} (depends on: {', '.join(t.depends_on) or 'none'})"
                for t in plan.tasks
            )
            memory.scratchpad["plan"] = tasks_repr
            memory.scratchpad["plan_dag"] = plan
            first_task = plan.task(ordered_tasks[0]) if ordered_tasks else None
            memory.scratchpad["current_subgoal"] = (
                f"[{first_task.id}] {first_task.instruction}" if first_task else None
            )
            return plan
    except Exception as e:
        print(f"[Plan Initialization Warning]: Could not decompose goal: {e}")
        return None


def run_static_plan(goal: str, llm: Optional[BaseChatModel] = None, max_workers: int = 4) -> str:
    """
    Decomposes a goal into a DAG plan, executes all task nodes in topological batches,
    and returns the final synthesized output.
    """
    base_llm = llm or get_base_llm()
    plan = decompose_goal(goal=goal, llm=base_llm)
    outputs = execute_plan(plan=plan, llm=base_llm, max_workers=max_workers)
    return final_output(plan=plan, outputs=outputs)


def run_dynamic_plan(goal: str, llm: Optional[BaseChatModel] = None, max_steps: int = 4) -> list[tuple[str, str]]:
    """
    Runs adaptive dynamic decomposition step-by-step until the goal is met.
    """
    base_llm = llm or get_base_llm()
    return dynamic_decomposition(goal=goal, llm=base_llm, max_steps=max_steps)


def build_structured_model(action_names: List[str]):
    step_model = build_agent_step_model(action_names)
    return init_chat_model(
        model=MODEL_NAME,
        model_provider=MODEL_PROVIDER,
        max_tokens=1024,
        temperature=0.1,
        max_retries=3,
    ).with_structured_output(step_model)



async def discover_tools(client) -> Dict[str, Any]:
    tools_list = await client.list_tools()
    return {tool.name: tool for tool in tools_list}


def validate_step(step: AgentStep, tools: Dict[str, Any]) -> bool:
    return step.action in TERMINAL_ACTIONS or step.action in tools


def handle_final_action(step: AgentStep) -> bool:
    """Check if the step represents a terminal state."""
    return step.action in TERMINAL_ACTIONS
    
async def execute_subtask_with_algorithm(
    task_instruction: Any,
    method: str = "plan_and_solve",
    context: str = "",
    llm: Optional[BaseChatModel] = None,
    environment: Optional[Any] = None,
    draft: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """
    Executes a sub-task using any of the planning and reasoning algorithms in the repository:
      - 'plan_and_solve' / 'ps': Plan-and-Solve 2-stage prompting.
      - 'tree_of_thoughts' / 'tree_of_thought' / 'tot': Tree of Thoughts beam search exploration.
      - 'lats' / 'lats_grounded': Language Agent Tree Search with grounded environment & value estimation.
      - 'lats_ungrounded': LATS with ungrounded baseline environment.
      - 'reflexion': Iterative trial loop with episodic memory & environment feedback.
      - 'self_refine' / 'refine': Iterative critique and refinement using rubric & deterministic checks.
      - 'static_decomposition' / 'dag' / 'plan': Full DAG task generation and parallel batch execution.
      - 'dynamic_decomposition' / 'dynamic': Adaptive step-by-step decision and execution loop.
    """
    base_llm = llm or get_base_llm()
    env = environment or GreenfieldEnvironment()

    task_str = task_instruction.instruction if hasattr(task_instruction, "instruction") else str(task_instruction)
    if context:
        task_str = f"Problem: {task_str}\nContext: {context}"

    normalized_method = method.lower().strip()
    if normalized_method in ("plan_and_solve", "ps"):
        return plan_and_solve(question=task_str, llm=base_llm)
    elif normalized_method in ("tree_of_thoughts", "tree_of_thought", "tot"):
        depth = kwargs.get("depth", 2)
        beam_width = kwargs.get("beam_width", 2)
        return tree_of_thoughts(problem=task_str, llm=base_llm, depth=depth, beam_width=beam_width)
    elif normalized_method in ("lats", "lats_grounded"):
        iterations = kwargs.get("iterations", 2)
        n_actions = kwargs.get("n_actions", 2)
        return lats(task=task_str, llm=base_llm, environment=env, iterations=iterations, n_actions=n_actions)
    elif normalized_method == "lats_ungrounded":
        ungrounded_env = environment or Environment(enable_domain_checks=False)
        iterations = kwargs.get("iterations", 2)
        return lats(task=task_str, llm=base_llm, environment=ungrounded_env, iterations=iterations)
    elif normalized_method == "reflexion":
        max_trials = kwargs.get("max_trials", 3)
        memory_size = kwargs.get("memory_size", 3)
        return reflexion(task=task_str, llm=base_llm, environment=env, max_trials=max_trials, memory_size=memory_size)
    elif normalized_method in ("self_refine", "refine"):
        target_draft = draft or kwargs.get("draft") or task_str
        return reflect_and_refine(goal=task_str, draft=target_draft, llm=base_llm)
    elif normalized_method in ("static_decomposition", "dag", "plan"):
        max_workers = kwargs.get("max_workers", 4)
        return run_static_plan(goal=task_str, llm=base_llm, max_workers=max_workers)
    elif normalized_method in ("dynamic_decomposition", "dynamic"):
        max_steps = kwargs.get("max_steps", 4)
        return run_dynamic_plan(goal=task_str, llm=base_llm, max_steps=max_steps)
    else:
        raise ValueError(f"Unknown planning algorithm method: {method}")



async def tool_call(client, step: AgentStep) -> Any:
    payload = step.action_input or {}

    # Validate schema using defined Pydantic model
    schema_cls = ACTION_INPUT_SCHEMAS.get(step.action)
    if schema_cls and isinstance(payload, dict):
        validated_input = schema_cls(**payload)
        payload = validated_input.model_dump()

    # Wrap payload for FastMCP tool signature expectations
    mcp_payload = {"input_data": payload} if payload else {}

    # Invoke tool via MCP client call interface
    result = await client.call_tool(step.action, mcp_payload)
    return result

async def assemble_system_prompt(
    memory: ShortTermMemory,
    user_input: str,
    tool_names: List[str],
) -> str:
    """
    Build the full system prompt by combining the planning scratchpad,
    long-term memory context (semantic facts + episodic events), and
    the tool-aware instruction template.

    This is a pure data-assembly step with one RAG-verification side-call
    to check fact relevance.
    """
    semantic_context = ""
    if hasattr(memory, "long_term"):
        active_facts = list(memory.long_term.get_active_facts().values())
        v_mem = self_rag_verify(user_input, active_facts, user_input)
        if v_mem.is_relevant:
            semantic_context += "\nVerified Known Facts:\n" + "\n".join([f"- {f}" for f in active_facts]) + "\n"
        if memory.long_term.semantic_facts:
            facts_list = [f"- {k}: {v}" for k, v in memory.long_term.semantic_facts.items()]
            semantic_context += "\nKnown Facts:\n" + "\n".join(facts_list) + "\n"

        if memory.long_term.episodic_events:
            # Take the 5 most recent episodic events
            events_list = [
                f"- {e.get('summary')}: Context={e.get('context')}, Outcome={e.get('outcome')}"
                for e in memory.long_term.episodic_events[-5:]
                if e.get("summary")
            ]
            if events_list:
                semantic_context += "\nPast Logged Events:\n" + "\n".join(events_list) + "\n"

    system_prompt = (
        f"Current plan: {memory.scratchpad.get('plan')}\n"
        f"Sub-goal: {memory.scratchpad.get('current_subgoal')}\n"
        f"{semantic_context}"
        f"{build_system_prompt(tool_names)}"
    )
    return system_prompt


async def handle_step_result(
    step: AgentStep,
    client,
    memory: ShortTermMemory,
    tools: Dict[str, Any],
    tool_names: List[str],
    user_input: str,
) -> Optional[AgentStep]:
    """
    Process a single agent step after LLM generation:
      1. Update the planning scratchpad if the step modified the plan.
      2. If the step is terminal, run Self-RAG verification and return it.
      3. If the action is invalid, record an error observation and return None.
      4. Otherwise execute the tool call and record the observation.

    Returns the step if it is terminal (caller should stop the loop),
    or None to signal that the loop should continue.
    """
    # Update planning scratchpad if the step modified it
    if getattr(step, "plan_updated", False):
        if getattr(step, "new_plan", None):
            memory.scratchpad["plan"] = step.new_plan
        if getattr(step, "next_subgoal", None):
            memory.scratchpad["current_subgoal"] = step.next_subgoal

    # Terminal action — verify grounding and return
    if handle_final_action(step):
        answer_text = str(step.action_input.get("answer") if isinstance(step.action_input, dict) else step.action_input)
        recent_context = [m.content for m in memory.get_context() if isinstance(m, HumanMessage)][-3:]
        v_result = self_rag_verify(user_input, recent_context, answer_text)

        if not v_result.is_supported:
            print(f"[Self-RAG Warning]: Answer lacks sufficient grounding ({v_result.reasoning})")
        return step

    # Invalid tool name — record error, signal continue
    if not validate_step(step, tools):
        memory.add_observation(
            f"Error: '{step.action}' is not a valid tool. Valid tools: {tool_names}"
        )
        return None

    # Execute the tool call
    try:
        result = await tool_call(client, step)
        print(f"Observation from {step.action}: {result}")
        memory.add_observation(f"Result from {step.action}: {result}")
    except ValidationError as e:
        err_msg = f"Invalid schema arguments for {step.action}: {e.errors()}"
        print(err_msg)
        memory.add_observation(err_msg)

    return None


async def execute_step_loop(
    client,
    memory: ShortTermMemory,
    tools: Dict[str, Any],
    tool_names: List[str],
    user_input: str,
) -> Optional[AgentStep]:
    """
    Run the agent's reason-act loop for up to MAX_STEPS iterations.

    Each iteration:
      1. Prune the conversation context via recursive summarization.
      2. Invoke the structured LLM to produce an AgentStep.
      3. Delegate post-processing to ``handle_step_result``.
    """
    model = build_structured_model(tool_names)

    for step_num in range(MAX_STEPS):
        print(f"\n--- Step {step_num + 1} ---")

        try:
            raw_context = memory.get_context()
            pruned_context = recursive_summarization(raw_context, model, keep_recent=6)
            step: AgentStep = await model.ainvoke(pruned_context)
        except Exception as e:
            print(f"[Agent Step Error]: {e}")
            memory.add_observation(f"Failed to generate structured step: {str(e)}")
            return None

        print(f"Thought: {step.thought}")
        print(f"Action: {step.action}")
        memory.add_ai(f"Thought: {step.thought}\nAction: {step.action}\nInput: {step.action_input}")

        result = await handle_step_result(
            step=step,
            client=client,
            memory=memory,
            tools=tools,
            tool_names=tool_names,
            user_input=user_input,
        )
        if result is not None:
            return result

    print("Reached maximum execution steps without a final answer.")
    return None


async def agent_step(
    client,
    memory: ShortTermMemory,
    user_input: str,
    llm: Optional[BaseChatModel] = None,
    use_dynamic_plan: bool = False,
) -> Optional[AgentStep]:
    """
    Top-level orchestrator that preserves the original public API.

    Pipeline:
      1. Record the user message and initialize the plan (if needed).
      2. Discover available MCP tools.
      3. Assemble the system prompt from memory + tools.
      4. Run the reason-act execution loop.
    """
    memory.add_user(user_input)

    # Initialize plan decomposition in scratchpad if not already populated
    if not memory.scratchpad.get("plan"):
        initialize_plan(user_input, memory, llm=llm, dynamic=use_dynamic_plan)

    tools = await discover_tools(client)
    current_tool_names = sorted(tools.keys())

    system_prompt = await assemble_system_prompt(
        memory=memory,
        user_input=user_input,
        tool_names=current_tool_names,
    )
    memory.set_system_prompt(system_prompt)

    return await execute_step_loop(
        client=client,
        memory=memory,
        tools=tools,
        tool_names=current_tool_names,
        user_input=user_input,
    )


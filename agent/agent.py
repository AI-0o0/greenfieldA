import asyncio
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from pydantic import ValidationError

from langchain.chat_models import init_chat_model

from .schema import (
    ACTION_INPUT_SCHEMAS,
    AgentStep,
    build_agent_step_model,
    TERMINAL_ACTIONS,
    MAX_STEPS,
)

from memory.memory import ShortTermMemory
load_dotenv()
from context_eval.strategies import recursive_summarization


def build_system_prompt(tool_names: List[str]) -> str:
    tool_list = "\n".join(sorted(tool_names))
    return f"""You are a constrained support agent.

Use ONLY these tools:
{tool_list}

Additional Instructions:
1. Do NOT retry calling a tool if you already received an Observation from it.
2. Once you have gathered enough information, set your action to 'final_answer' and provide the response in 'action_input.answer'.
3. Do NOT invent or call tools that are not listed above.
4. If a tool call fails, try a different tool if relevant; do NOT retry the same tool with identical inputs.
5. If you cannot answer using available tools, set your action to 'escalate' to hand off to human support.
6. If the user input does not require tools, set your action to 'final_answer' directly.
7. If the user input is ambiguous or lacks necessary details (e.g., greetings, general help requests, personal statements), do NOT invoke tools. Set your action to 'final_answer' directly.
8. Only use 'log_incident_note' for actual physical farm incidents, chemical spills, or equipment damage.

Think step by step and return only the structured response."""


def build_structured_model(action_names: List[str]):
    step_model = build_agent_step_model(action_names)
    return init_chat_model(
        model="llama-3.3-70b-versatile",
        model_provider="groq",
        max_tokens=1024,
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


async def agent_step(client, memory: ShortTermMemory, user_input: str) -> Optional[AgentStep]:
    memory.add_user(user_input)

    tools = await discover_tools(client)
    current_tool_names = sorted(tools.keys())

    # Extract semantic facts and recent episodic events
    semantic_context = ""
    if hasattr(memory, "long_term"):
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
        f"{build_system_prompt(current_tool_names)}"
    )
    memory.set_system_prompt(system_prompt)
    memory.set_system_prompt(system_prompt)

    model = build_structured_model(current_tool_names)

    for step_num in range(MAX_STEPS):
        print(f"\n--- Step {step_num + 1} ---")

        try:
            # implement recursive summarization as a context management strategy 
            raw_context = memory.get_context() 
            pruned_context = recursive_summarization(raw_context, model, keep_recent=6)
            step: AgentStep = await model.ainvoke(pruned_context)

        except Exception as e:
            memory.add_observation(f"Failed to generate structured step: {str(e)}")
            return None

        print(f"Thought: {step.thought}")
        print(f"Action: {step.action}")
        memory.add_ai(f"Thought: {step.thought}\nAction: {step.action}\nInput: {step.action_input}")

        # Update planning scratchpad if updated in step
        if getattr(step, "plan_updated", False):
            memory.scratchpad["plan"] = getattr(step, "new_plan", None)
            memory.scratchpad["current_subgoal"] = getattr(step, "next_subgoal", None)

        if handle_final_action(step):
            return step

        if not validate_step(step, tools):
            memory.add_observation(
                f"Error: '{step.action}' is not a valid tool. Valid tools: {current_tool_names}"
            )
            continue

        try:
            result = await tool_call(client, step)
            print(f"Observation from {step.action}: {result}")
            memory.add_observation(f"Result from {step.action}: {result}")
        except ValidationError as e:
            memory.add_observation(f"Invalid arguments for {step.action}: {e.errors()}")
        except Exception as e:
            print(f"Tool Execution Error: {e}")
            memory.add_observation(f"Error executing tool {step.action}: {str(e)}")

    print("Reached maximum execution steps without a final answer.")
    return None
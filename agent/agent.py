import asyncio
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from pydantic import ValidationError

from langchain.chat_models import init_chat_model
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    BaseMessage,
)

from .schema import (
    ACTION_INPUT_SCHEMAS,
    AgentStep,
    build_agent_step_model,
    TERMINAL_ACTIONS,
    MAX_STEPS,
)

class ShortTermMemory:
    def __init__(self, max_turns: int = 20):
        self.max_turns = max_turns
        self.messages: List[BaseMessage] = []
        self.scratchpad: Dict[str, Any] = {}

    def set_system_prompt(self, content: str):
        """Maintains a single active system prompt at the root."""
        if self.messages and isinstance(self.messages[0], SystemMessage):
            self.messages[0] = SystemMessage(content=content)
        else:
            self.messages.insert(0, SystemMessage(content=content))

    def add_user(self, content: str):
        self.messages.append(HumanMessage(content=content))
        self._truncate()

    def add_ai(self, content: str):
        self.messages.append(AIMessage(content=content))
        self._truncate()

    def add_observation(self, content: str):
        self.messages.append(HumanMessage(content=f"[Observation]: {content}"))
        self._truncate()

    def _truncate(self):
        # Preserve SystemMessage at index 0 while truncating history
        if len(self.messages) > self.max_turns + 1:
            system_msg = [self.messages[0]] if isinstance(self.messages[0], SystemMessage) else []
            history = self.messages[1:] if system_msg else self.messages
            self.messages = system_msg + history[-self.max_turns:]

    def get_context(self) -> List[BaseMessage]:
        return self.messages
load_dotenv()


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


async def tool_call(step: AgentStep, tools: Dict[str, Any]) -> Any:
    tool = tools[step.action]
    payload = step.action_input or {}

    # Validate schema if defined
    schema_cls = ACTION_INPUT_SCHEMAS.get(step.action)
    if schema_cls and isinstance(payload, dict):
        validated_input = schema_cls(**payload)
        payload = validated_input.model_dump()

    # Invoke tool safely (handles async & sync tools via LangChain interface)
    if hasattr(tool, "ainvoke"):
        return await tool.ainvoke(payload)
    elif callable(tool):
        if isinstance(payload, dict):
            return await asyncio.to_thread(tool, **payload)
        return await asyncio.to_thread(tool, payload)
    else:
        raise ValueError(f"Tool {step.action} is not invokable.")


async def agent_step(client, memory: ShortTermMemory, user_input: str) -> Optional[AgentStep]:
    memory.add_user(user_input)

    tools = await discover_tools(client)
    current_tool_names = sorted(tools.keys())

    # Build system prompt without duplicating
    system_prompt = (
        f"Current plan: {memory.scratchpad.get('plan')}\n"
        f"Sub-goal: {memory.scratchpad.get('current_subgoal')}\n"
        f"{build_system_prompt(current_tool_names)}"
    )
    memory.set_system_prompt(system_prompt)

    model = build_structured_model(current_tool_names)

    for step_num in range(MAX_STEPS):
        print(f"\n--- Step {step_num + 1} ---")

        try:
            step: AgentStep = await model.ainvoke(memory.get_context())
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
            result = await tool_call(step, tools)
            print(f"Observation from {step.action}: {result}")
            memory.add_observation(f"Result from {step.action}: {result}")
        except ValidationError as e:
            memory.add_observation(f"Invalid arguments for {step.action}: {e.errors()}")
        except Exception as e:
            memory.add_observation(f"Error executing tool {step.action}: {str(e)}")

    print("Reached maximum execution steps without a final answer.")
    return None
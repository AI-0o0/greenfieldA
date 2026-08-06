import asyncio
from dotenv import load_dotenv
from dataclasses import dataclass
from pydantic import ValidationError
from langchain.chat_models import init_chat_model
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from .schema import (
    ACTION_INPUT_SCHEMAS,
    AgentStep,
    build_agent_step_model,
    TERMINAL_ACTIONS,
    MAX_STEPS,
)



load_dotenv()


@dataclass
class AgentContext:
    user_id: str


@dataclass
class ToolRuntimeShim:
    context: AgentContext


def build_system_prompt(tool_names):

    tool_list = "\n".join(tool_names)

    return f"""
You are a constrained support agent.

Use ONLY these tools:
{tool_list}
Additional Instructions:
1. Do NOT retry calling a tool if you already received an Observation from it.
2. Once you have gathered enough information to answer the user's question, set your action to 'final_answer' and provide the final response in 'action_input.answer'.
3. Do NOT invent or call tools that are not listed above.
4. if a tool call fails, you may try a different tool if relevant, but do NOT retry the same tool with the same input.
5. If you cannot answer the user's question with the available tools, set your action to 'escalate' to hand off to a human support agent.
6. if the user input dosent need any tools dont call any tools and just answer the user directly.
Think step by step and return only the structured response.
"""

# def build_structured_model():
#     return init_chat_model(
#         model="google_genai:gemini-3.5-flash-lite",
#         max_tokens=1024,
#         max_retries=3,
#     ).with_structured_output(AgentStep)

#groq
def build_structured_model(action_names):
    """Rebuilds the structured-output schema from whatever tools are
    live right now, so a runtime tool-list change (e.g. VIP unlock)
    immediately changes what the LLM is allowed to output."""
    step_model = build_agent_step_model(action_names)
    return init_chat_model(
        model="llama-3.3-70b-versatile",
        model_provider="groq",
        max_tokens=1024,
        max_retries=3,
    ).with_structured_output(step_model)


async def discover_tools(client):
    """Dynamically fetches and registers available tools from the MCP Client."""
    tools_list = await client.list_tools()
    # turns from list to dict
    tools_dict = {tool.name: tool for tool in tools_list}

    return tools_dict  # Dict: {tool_name: tool_instance}

  
def validate_step(step, tools) -> bool:
    return step.action in TERMINAL_ACTIONS or step.action in tools


async def tool_call(step: AgentStep, tools: dict, context: AgentContext = None):
    """Validates payload schema, injects runtime context, and executes tool."""
    tool = tools[step.action]

    payload = step.action_input

    # 1. Pydantic validation if schema exists
    schema_cls = ACTION_INPUT_SCHEMAS.get(step.action)
    if schema_cls:
        validated_input = schema_cls(**step.action_input)
        payload = validated_input.model_dump()

    # 2. Inject context (user_id) if missing
    if context and isinstance(payload, dict):
        if step.action in {
            "get_booking_history",
            "get_customer_profile",
        }:
            payload.setdefault("user_id", context.user_id)
    # 3. Asynchronous execution
    result = await tool.ainvoke(payload)
    return result

def handle_final_action(step):

    if step.action == "final_answer":
        print(step.action_input["answer"])
        return True

    if step.action == "end_conversation":
        if step.action_input:
            print(step.action_input.get("answer", "Goodbye!"))
        else:
            print("Goodbye!")
        return True

    if step.action == "escalate":
        print("Escalating to human support...")
        return True

    return False

#observation
def handle_tool_result(messages, step, result):
    print(f"Observation from {step.action}: {result}")
    messages.append(
        HumanMessage(
            content=f"Observation from {step.action}: {result}"
        )
    )

conversation_history = {}
known_tools_by_user = {}

async def run_agent(client, user_input: str, user_id: str = "C001"):
    tools = await discover_tools(client)
    current_tool_names = set(tools.keys())
    context = AgentContext(user_id=user_id)
    system_prompt = build_system_prompt(sorted(current_tool_names))
    model = build_structured_model(list(current_tool_names))

    if user_id not in conversation_history:
        conversation_history[user_id] = [
            SystemMessage(content=system_prompt)
        ]
    else:
        previous_tool_names = known_tools_by_user.get(user_id, current_tool_names)
        newly_available = current_tool_names - previous_tool_names
        if newly_available:

            conversation_history[user_id][0] = SystemMessage(content=system_prompt)
            conversation_history[user_id].append(
                HumanMessage(
                    content=(
                        "SYSTEM NOTICE: New tools just became available: "
                        f"{', '.join(sorted(newly_available))}. "
                        "You may use them starting now if relevant."
                    )
                )
            )
            print(
                f"\n[agent] Tool list changed mid-conversation for {user_id}: "
                f"+{sorted(newly_available)}"
            )

    known_tools_by_user[user_id] = current_tool_names

    messages = conversation_history[user_id]
    messages.append(HumanMessage(content=user_input))

    # (Agent Loop)
    for step_num in range(MAX_STEPS):
        print(f"\n--- Step {step_num + 1} ---")
        
        step: AgentStep = await model.ainvoke(messages)
        print(f"Thought: {step.thought}")
        print(f"Action: {step.action}")
        messages.append(
            AIMessage(content=f"Thought: {step.thought}\nAction: {step.action}\nInput: {step.action_input}")
        )
        #(Final Action)
        if handle_final_action(step):
            return step
        
        #  Step Validation check
        if not validate_step(step, tools):
            messages.append(
                HumanMessage(
                    content=f"Error: '{step.action}' is not a valid tool. Choose from: {list(tools.keys())}"
                )
            )
            continue


        # (MCP Tool Execution)
        try:
            result = await tool_call(step, tools, context=context)
            handle_tool_result(messages, step, result)

        except ValidationError as e:
            messages.append(
                HumanMessage(content=f"Invalid arguments for {step.action}: {e.errors()}")
            )
        except Exception as e:
            messages.append(
                HumanMessage(content=f"Error executing tool {step.action}: {str(e)}")
            )
    print("Reached maximum execution steps without final answer.")
    return None



if __name__ == "__main__":
    pass
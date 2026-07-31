import asyncio
import json
import os
import sys
import mcp.types as types
from dotenv import load_dotenv
from groq import AsyncGroq
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

load_dotenv()

async def elicitation_callback(context, params: types.ElicitRequestParams) -> types.ElicitResult:
    print(f"\n[HUMAN SIGN-OFF REQUESTED BY SERVER]: {params.message}")
    
    # Simulating a human approving 
    decision = {"approved": True, "notes": "Approved by automated test runner"}
    
    print(f"[HUMAN RESPONDS]: {decision}\n")
    return types.ElicitResult(action="accept", content=decision)

async def main():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("Error: GROQ_API_KEY is missing!")
        return

    # reading tests
    tests_file = "agent/tests.json"
    if not os.path.exists(tests_file):
        print(f"Error: {tests_file} not found!")
        return

    with open(tests_file, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    groq_client = AsyncGroq(api_key=api_key)
    model = "llama-3.3-70b-versatile"
    # model = "llama-3.1-8b-instant"

    server_params = StdioServerParameters(command="python", args=["mcp_server/server.py"])
    print("Connecting to server...")

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(
            read_stream, 
            write_stream, 
            elicitation_callback=elicitation_callback
        ) as session:
            
            init_result = await session.initialize()
            if init_result.capabilities.resources is None:
                print("[WARN] server doesn't support resources — skipping resource checks")
                
            tools_result = await session.list_tools()
            llm_tools = []
            for t in tools_result.tools:
                schema = t.inputSchema.copy()
                if "$schema" in schema:
                    del schema["$schema"]
                llm_tools.append({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": schema
                    }
                })

            # looping on all test cases
            for index, test in enumerate(test_cases, 1):
                print(f"==================================================")
                print(f"RUNNING {test['id']}: {test['description']}")
                print(f"PROMPT: {test['prompt']}")
                print(f"==================================================")

                messages = [
                    {
                        "role": "system", 
                        "content": (
                            "You are a helpful farm assistant. You MUST use the provided tools to fulfill requests. "
                            "If a tool succeeds or returns an error, report it and STOP immediately."
                        )
                    },
                    {
                        "role": "user",
                        "content": test['prompt']
                    }
                ]

                loop_count = 0
                while True:
                    loop_count += 1
                    if loop_count > 5:
                        print("[SYSTEM]: Loop limit reached for this test. Moving on.")
                        break

                    response = await groq_client.chat.completions.create(
                        model=model,
                        messages=messages,
                        tools=llm_tools,
                        temperature=0,
                        tool_choice="auto"
                    )

                    msg = response.choices[0].message
                    messages.append(msg.model_dump(exclude_none=True))

                    if not msg.tool_calls:
                        print(f"\n🤖 [AGENT FINAL ANSWER]: {msg.content}\n")
                        break

                    tool_executed = False
                    for tool_call in msg.tool_calls:
                        args = json.loads(tool_call.function.arguments)
                        print(f"\n🧠 [MODEL CALLS TOOL]: {tool_call.function.name}({args})")
                        
                        try:
                            result = await session.call_tool(tool_call.function.name, args)
                            result_text = result.content[0].text if result.content else "no content"
                        except Exception as e:
                            result_text = f"Error: {str(e)}"
                            
                        print(f"⚙️ [TOOL RESULT]: {result_text}")
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.function.name,
                            "content": result_text
                        })
                        tool_executed = True

                    if tool_executed:
                        pass
                        
                    print(f"✅ Finished {test['id']}\n")

if __name__ == "__main__":
    asyncio.run(main())
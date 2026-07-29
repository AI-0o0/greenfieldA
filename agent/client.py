import asyncio
from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession
import mcp.types as types

async def run_demo():
    server_cmd = "python"
    server_args = ["../mcp_server/server.py"]

    print("=== Task 9: End-to-End Agent Demo ===")
    
    async with stdio_client(server_cmd, server_args) as (read_stream, write_stream):
        # Enable experimental capabilities for Elicitation
        capabilities = types.ClientCapabilities(
            experimental={"elicitation": {}}
        )
        
        async with ClientSession(read_stream, write_stream) as session:
            # 1. Capability Negotiation Handshake
            await session.initialize(capabilities=capabilities)
            print("[+] Handshake complete. Capabilities negotiated.")

            # 2. Initial Tool List (Task 7 Setup)
            tools_response = await session.list_tools()
            print("\n[+] Initial Tools (Read-Only/Basic):")
            for t in tools_response.tools:
                print(f"  - {t.name}")

            # 3. Trigger Runtime Notification via Authentication (Task 7)
            print("\n[+] Authenticating Technician to trigger tools/list_changed...")
            auth_res = await session.call_tool("authenticate_technician", {"technician_id": 99})
            print(f"  Result: {auth_res.content[0].text}")

            updated_tools = await session.list_tools()
            print("\n[+] Updated Tools (override_emergency_stop should now be visible):")
            for t in updated_tools.tools:
                print(f"  - {t.name}")

            # 4. Trigger Progress Tracking (Task 8)
            print("\n[+] Executing batch_dispatch to test Progress Tracking...")
            # Note: In a real client, progress events are handled via a callback/handler attached to the session
            batch_res = await session.call_tool("batch_dispatch", {"equipment_ids": [101, 102, 103], "field_id": 5})
            print(f"  Result: {batch_res.content[0].text}")

            # 5. Trigger LLM Sampling (Task 8)
            print("\n[+] Executing log_incident_note to test LLM Sampling...")
            # Note: The server will send a createMessage request back to this client's environment
            incident_res = await session.call_tool("log_incident_note", {"raw_note": "Tractor 101 wheel broke and leaking oil."})
            print(f"  Result: {incident_res.content[0].text}")

            print("\n=== Demo Execution Finished ===")

if __name__ == "__main__":
    asyncio.run(run_demo())

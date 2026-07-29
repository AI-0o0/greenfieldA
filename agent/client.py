import asyncio
from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession
import mcp.types as types

async def run_demo():
    server_cmd = "python"
    server_args = ["../mcp_server/server.py"]

    print("=== Task 9: End-to-End Agent Demo ===")
    
    async with stdio_client(server_cmd, server_args) as (read_stream, write_stream):
        # Enable experimental capabilities for Elicitation (Required for Task 5 & 6)
        capabilities = types.ClientCapabilities(
            experimental={"elicitation": {}}
        )
        
        async with ClientSession(read_stream, write_stream) as session:
            # 1. Capability Negotiation Handshake (Task 6)
            await session.initialize(capabilities=capabilities)
            print("[+] Handshake complete. Capabilities negotiated.")

            # 2. Fetch Resources & Prompts (Task 2 - Role 1)
            print("\n[+] Testing Resources & Prompts (Role 1)...")
            try:
                prompts = await session.list_prompts()
                print(f"  - Prompts discovered: {[p.name for p in prompts.prompts]}")
                resources = await session.list_resources()
                print(f"  - Resources discovered: {[r.name for r in resources.resources]}")
            except Exception as e:
                print("  - Role 1 tasks not fully implemented yet, skipping...")

            # 3. Initial Tool List (Task 7 Setup)
            tools_response = await session.list_tools()
            print("\n[+] Initial Tools (Read-Only/Basic):")
            for t in tools_response.tools:
                print(f"  - {t.name}")

            # 4. Trigger Runtime Notification via Authentication (Task 7)
            print("\n[+] Authenticating Technician to trigger tools/list_changed...")
            auth_res = await session.call_tool("authenticate_technician", {"technician_id": 99})
            print(f"  Result: {auth_res.content[0].text}")

            updated_tools = await session.list_tools()
            print("\n[+] Updated Tools (override_emergency_stop should now be visible):")
            for t in updated_tools.tools:
                print(f"  - {t.name}")

            # 5. Trigger Progress Tracking (Task 8)
            print("\n[+] Executing batch_dispatch to test Progress Tracking...")
            batch_res = await session.call_tool("batch_dispatch", {"equipment_ids": [101, 102], "field_id": 5})
            print(f"  Result: {batch_res.content[0].text}")

            # 6. Trigger LLM Sampling (Task 8)
            print("\n[+] Executing log_incident_note to test LLM Sampling...")
            incident_res = await session.call_tool("log_incident_note", {"raw_note": "Tractor 101 wheel broke."})
            print(f"  Result: {incident_res.content[0].text}")

            # 7. Trigger Elicitation Pause (Task 5 - Role 2)
            print("\n[+] Executing dispatch_equipment to test Elicitation (Human-in-the-loop)...")
            try:
                # Dispatching with a chemical_id to trigger the danger signoff
                dispatch_res = await session.call_tool("dispatch_equipment", {
                    "equipment_id": 103, 
                    "field_id": 2, 
                    "job_type": "spray", 
                    "chemical_id": 1, 
                    "customer_id": 1
                })
                print(f"  Result: {dispatch_res.content[0].text}")
            except Exception as e:
                # If the database isn't fully seeded by Role 1, it might raise an error, but the attempt is logged.
                print(f"  - Elicitation/Dispatch response: {str(e)}")

            print("\n=== Demo Execution Finished ===")

if __name__ == "__main__":
    asyncio.run(run_demo())

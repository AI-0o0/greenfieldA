import asyncio
import os
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession
import mcp.types as types

async def run_demo():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    server_script = os.path.normpath(os.path.join(current_dir, "..", "mcp_server", "server.py"))

    server_params = StdioServerParameters(
        command="python",
        args=[server_script]
    )

    print("=== Task 9: End-to-End Agent Demo ===")
    
    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # 1. Capability Negotiation Handshake
            await session.initialize()
            print("[+] Handshake complete. Capabilities negotiated.")

            # 2. Testing Task 2 (Resources & Prompts)
            print("\n[+] Testing Task 2 (Resources & Prompts)...")
            try:
                prompts = await session.list_prompts()
                print("  - Prompts module is ready.")
            except Exception:
                print("  - Role 1 tasks (Resources/Prompts) not fully implemented yet, skipping gracefully...")

            # 3. Trigger Task 7 (Runtime Notifications via Payment)
            print("\n[+] Triggering Task 7 (Notifications)...")
            print("  - Processing payment to clear credit hold and unlock dispatch...")
            try:
                pay_res = await session.call_tool("process_payment", {"input_data": {"customer_id": 1}})
                print(f"  - Result: {pay_res.content[0].text}")
                
                await session.list_tools()
                print("  - Tool list refreshed automatically after notification.")
            except Exception as e:
                print(f"  - Warning: {str(e)}")

            # 4. Trigger Task 8 (Progress Tracking)
            print("\n[+] Triggering Task 8 (Progress Tracking)...")
            try:
                batch_res = await session.call_tool("batch_dispatch", {"input_data": {"equipment_ids": [101, 102], "field_id": 5}})
                print(f"  - Result: {batch_res.content[0].text}")
            except Exception as e:
                 print(f"  - Warning: {str(e)}")

            # 5. Trigger Task 8 (LLM Sampling)
            print("\n[+] Triggering Task 8 (LLM Sampling)...")
            try:
                incident_res = await session.call_tool("log_incident_note", {"input_data": {"raw_note": "Tractor 101 leaking oil near the river."}})
                print(f"  - Result: {incident_res.content[0].text}")
            except Exception as e:
                 print(f"  - Warning: {str(e)}")

            print("\n=== Demo Execution Finished ===")

if __name__ == "__main__":
    asyncio.run(run_demo())
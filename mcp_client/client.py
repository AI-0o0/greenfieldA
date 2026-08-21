import asyncio
import os
import sys
from contextlib import asynccontextmanager

from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult, ElicitRequestParams, RequestContext



path_to_mcp_server = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "mcp_server", "server.py")
)

mode = sys.argv[1] if len(sys.argv) > 1 else "stdio"


async def on_progress(progress: float, total: float | None, message: str | None):
    """Handle progress notifications from the server."""
    percent = progress
    if total:
        percent = (progress / total) * 100

    print(f"\n[Progress] {percent:.0f}% - {message}")


async def on_elicitation(
    message: str,
    response_type: type | None,
    params: ElicitRequestParams,
    context: RequestContext,
):
    """Handle elicitation requests (user input) from the server."""
    print("\n" + "=" * 50)
    print("REFUND CONFIRMATION")
    print("=" * 50)
    print(message)

    answer = input("\nType 'confirm' or 'cancel': ").strip().lower()

    if answer == "confirm":
        return ElicitResult(
            action="accept",
            content={"value": "confirm"}
        )

    return ElicitResult(action="decline")


@asynccontextmanager
async def create_client(mode: str = "stdio"):
    # 1. Build the configuration dictionary based on the transport mode
    if mode == "stdio":
        config = {
            "mcpServers": {
                "GREENFIELD_server": {
                    "command": sys.executable,
                    "args": [path_to_mcp_server, "stdio"],
                }
            }
        }
    elif mode == "http":
        config = {
            "mcpServers": {
                "GREENFIELD_server": {
                    "url": "http://127.0.0.1:8000/mcp",
                }
            }
        }
    else:
        raise ValueError(f"Invalid mode: {mode}. Must be 'stdio' or 'http'.")
        
    # 2. Initialize the fastmcp Client with our handlers
    client = Client(
        config,
        elicitation_handler=on_elicitation,
        progress_handler=on_progress,
    )

    # 3. Enter the async context to manage the connection lifecycle
    async with client:
        # Resource Discovery
        try:
            resources = await client.list_resources()
            for resource in resources:
                uri = str(resource.uri)
                try:
                    await client.read_resource(uri)
                except Exception:
                    pass
        except Exception:
            pass
                    
        # Prompt Discovery
        try:
            await client.list_prompts()
        except Exception:
            pass

        # Tool Discovery
        try:
            tools = await client.list_tools()
            create_client.last_tools = tools
        except Exception:
            pass

        # Yield the connected client so the caller can use it while it stays connected
        yield client
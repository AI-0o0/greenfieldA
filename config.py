import os

MODEL_NAME = "ministral-3b-2512"
MODEL_PROVIDER = "mistralai"

# ------------------------------------------------------------
# MCP server location (single source of truth).
# The streamable-http server binds this port (mcp_server/server.py)
# and every client connects to this URL (mcp_client/client.py,
# website/backend). Previously these two drifted apart (:8000 vs :8080).
# ------------------------------------------------------------
MCP_HOST = os.environ.get("GREENFIELD_MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("GREENFIELD_MCP_PORT", "8080"))
MCP_SERVER_URL = os.environ.get(
    "GREENFIELD_MCP_URL", f"http://{MCP_HOST}:{MCP_PORT}/mcp"
)

# Platform (website/backend FastAPI) bind settings
PLATFORM_HOST = os.environ.get("GREENFIELD_PLATFORM_HOST", "127.0.0.1")
PLATFORM_PORT = int(os.environ.get("GREENFIELD_PLATFORM_PORT", "8000"))
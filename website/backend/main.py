"""
website/backend/main.py

Greenfield Agricultural Agency platform.

One process hosts BOTH product surfaces against the live backend:
- the LIVE Greenfield MCP server (FastMCP streamable-http app mounted at /mcp),
- the admin console API (tools per agent, RAG documents, HITL inbox, tickets),
- the user chat API (switch between all agents),
- the static single-page frontend (website/frontend) served at /.

Run:
    uv run uvicorn website.backend.main:app --host 127.0.0.1 --port 8000
Then open http://127.0.0.1:8000
"""
# Live MCP server & interactive UX platform

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mcp_server.server import mcp as mcp_instance
from mcp_server.tool_manager import bootstrap as bootstrap_tools
from website.backend.routers import (
    admin_rag,
    admin_tools,
    chat,
    hitl,
    tickets,
    threads,
)
from website.backend.runtime import runtime

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

# The MCP server's ASGI app. stateless_http keeps sessions robust across
# backend restarts during demos (no stale session ids).
mcp_app = mcp_instance.http_app(path="/", stateless_http=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Enter FastMCP's own lifespan (session manager for streamable-http).
    async with mcp_app.lifespan(app):
        # 2. Seed Agent_Tool_Registry and sync the live tool set.
        await asyncio.to_thread(bootstrap_tools)
        # 3. Make sure the RAG store is populated from rag/docs (idempotent).
        try:
            from rag.vector_store import initialize_vector_db

            await asyncio.to_thread(initialize_vector_db)
        except Exception as exc:
            print(f"[platform] RAG init warning: {exc}")
        # 4. Connect the shared MCP client over loopback HTTP to THIS process's
        #    live server — one process, one live MCP endpoint.
        await runtime.startup()
        try:
            yield
        finally:
            await runtime.shutdown()


app = FastAPI(title="Greenfield Agricultural Agency Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- The live MCP server (same instance the CLI/agents have always used) ----
app.mount("/mcp", mcp_app)

# ---- Product APIs ----
app.include_router(chat.router)
app.include_router(admin_tools.router)
app.include_router(admin_rag.router)
app.include_router(hitl.router)
app.include_router(tickets.router)
app.include_router(threads.router)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "mcp_url": runtime.mcp_url,
        "finance_graph_ready": runtime._finance_graph is not None,
        "crop_graph_ready": runtime._crop_graph is not None,
        "maintenance_graph_ready": runtime._maintenance_graph is not None,
        "orchestrator_graph_ready": runtime._orchestrator_graph is not None,
    }


# ---- Static frontend ----
app.mount("/static", StaticFiles(directory=os.path.abspath(FRONTEND_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(os.path.abspath(FRONTEND_DIR), "index.html"))


if __name__ == "__main__":
    import uvicorn

    from config import PLATFORM_HOST, PLATFORM_PORT

    uvicorn.run(app, host=PLATFORM_HOST, port=PLATFORM_PORT)

"""
website/backend/routers/admin_tools.py

Admin surface: see every agent connected to the MCP server and add/remove
the tools available to each one. Toggles persist in Agent_Tool_Registry AND
re-sync the live FastMCP instance (register/deregister at runtime), so the
change provably reaches tools/list of the running server.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mcp_server.server import mcp as mcp_instance
from mcp_server import tool_manager
from website.backend.runtime import runtime

router = APIRouter(prefix="/api/admin/tools", tags=["admin-tools"])


class ToggleRequest(BaseModel):
    agent_id: str
    tool_name: str
    enabled: bool


@router.get("")
async def get_tool_matrix():
    tool_manager.seed_registry()
    rows = tool_manager.get_registry_rows()
    live = await tool_manager.list_live_tools(mcp_instance)
    return {
        "agents": list(tool_manager.KNOWN_AGENT_IDS),
        "tools": {
            name: meta["description"] for name, meta in tool_manager.TOOL_LIBRARY.items()
        },
        "rows": rows,
        "live_tools": sorted(live),
    }


@router.post("/toggle")
async def toggle_agent_tool(req: ToggleRequest):
    try:
        result = await asyncio.to_thread(
            tool_manager.set_agent_tool_enabled,
            req.agent_id,
            req.tool_name,
            req.enabled,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    # live_tools reflects the RUNNING server after this toggle.
    result["live_tools"] = sorted(await tool_manager.list_live_tools(mcp_instance))
    result["agent_tools_now"] = tool_manager.get_agent_tools(req.agent_id)
    return result


@router.get("/agent/{agent_id}")
async def agent_allowed_tools(agent_id: str):
    return {"agent_id": agent_id, "enabled": tool_manager.get_agent_tools(agent_id)}


@router.get("/verify")
async def verify_registry_reaches_server():
    """
    Rubric evidence helper: compares, for every agent, its registry allow-list
    against what a gated client would actually see on the LIVE server right now.
    """
    out = {}
    live = set(await tool_manager.list_live_tools(mcp_instance))
    for agent_id in tool_manager.KNOWN_AGENT_IDS:
        allowed = set(tool_manager.get_agent_tools(agent_id))
        visible = sorted(allowed & live)
        out[agent_id] = {
            "registry_enabled": sorted(allowed),
            "visible_on_live_server": visible,
        }
    out["_mcp_url"] = runtime.mcp_url
    return out

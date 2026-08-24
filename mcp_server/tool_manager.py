"""
mcp_server/tool_manager.py

Runtime tool registration / deregistration for the Greenfield MCP server,
driven by the Agent_Tool_Registry table (db/schema.sql:331) and controlled
from the platform's admin console (website/backend -> /api/admin/tools).

Rubric pointers:
- TOOL_LIBRARY:        every tool implementation the server can host
- register_tool() /
  deregister_tool():   mutate the LIVE FastMCP instance at runtime
                       (FastMCP add_tool / remove_tool)
- set_agent_tool_enabled()
  / get_agent_tools(): per-agent gating persisted in Agent_Tool_Registry;
                       this is what "add/remove tools available to each
                       agent" means in this system
- sync_server_from_registry():
                       a tool is live on the server iff at least one agent
                       has it enabled; startup + every toggle re-syncs, so
                       the platform's toggles provably reach tools/list

Note on change notifications: FastMCP cannot push notifications/tools/
list_changed to sessions from outside an active request. Platform agents
therefore re-run list_tools() each turn (see website/backend), so a toggle
takes effect immediately for every consumer; process_payment keeps its
in-request send_tool_list_changed() notification.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from mcp_server.tools import (
    search_agricultural_knowledge,
    process_payment,
    batch_dispatch,
    log_incident_note,
    dispatch_equipment_mcp,
    generate_fleet_report,
    get_equipment_status,
    get_db_connection,
)

# Agent identities known to the platform.
KNOWN_AGENT_IDS = (
    "orchestrator",
    "crop_disease",
    "finance",
    "maintenance",
    "knowledge_assistant",
    "fleet_planner",
)

# Tools always registered at server startup (backward compatibility with
# stdio consumers: main.py REPL, mcp_client, tests).
CORE_TOOLS = frozenset(
    {
        "search_agricultural_knowledge",
        "process_payment",
        "batch_dispatch",
        "log_incident_note",
        "dispatch_equipment",   # registered via the wire-safe wrapper
        "get_equipment_status",
        "generate_fleet_report",
    }
)


def _build_library() -> Dict[str, dict]:
    return {
        "search_agricultural_knowledge": {
            "fn": search_agricultural_knowledge,
            "description": "Search internal agricultural manuals, chemical compliance policies, and operating procedures.",
        },
        "process_payment": {
            "fn": process_payment,
            "description": "Process a customer payment to clear their credit hold and unlock dispatch tools.",
        },
        "batch_dispatch": {
            "fn": batch_dispatch,
            "description": "Batch-dispatch multiple pieces of equipment with progress updates.",
        },
        "log_incident_note": {
            "fn": log_incident_note,
            "description": "Log an unstructured incident note from the field.",
        },
        # Wire-safe wrapper: never exposes pre_approved over MCP (see tools.py).
        "dispatch_equipment": {
            "fn": dispatch_equipment_mcp,
            "description": "Dispatch equipment for till/harvest/spray jobs; restricted chemicals require human sign-off.",
        },
        "generate_fleet_report": {
            "fn": generate_fleet_report,
            "description": "Generate and store a monthly fleet utilization report.",
        },
        "get_equipment_status": {
            "fn": get_equipment_status,
            "description": "Snapshot every machine's current status and location.",
        },
    }


TOOL_LIBRARY: Dict[str, dict] = _build_library()


# ==============================================================
# Agent_Tool_Registry CRUD (per-agent availability)
# ==============================================================

def seed_registry(db_path: Optional[str] = None) -> None:
    """Ensures every known agent has a row for every library tool with least privilege."""
    defaults_disabled = {
        # Knowledge / Front-Desk assistant is read-only
        ("knowledge_assistant", "dispatch_equipment"),
        ("knowledge_assistant", "batch_dispatch"),
        ("knowledge_assistant", "process_payment"),
        ("knowledge_assistant", "generate_fleet_report"),
        # Crop disease: no payment or fleet reports
        ("crop_disease", "process_payment"),
        ("crop_disease", "generate_fleet_report"),
        ("crop_disease", "batch_dispatch"),
        # Finance: only payments and knowledge policies
        ("finance", "dispatch_equipment"),
        ("finance", "batch_dispatch"),
        ("finance", "get_equipment_status"),
        ("finance", "generate_fleet_report"),
        # Maintenance: no dispatch or payment
        ("maintenance", "dispatch_equipment"),
        ("maintenance", "batch_dispatch"),
        ("maintenance", "process_payment"),
        ("maintenance", "generate_fleet_report"),
        # Fleet Planner: no payment processing
        ("fleet_planner", "process_payment"),
    }
    conn = get_db_connection()
    try:
        for agent_id in KNOWN_AGENT_IDS:
            for tool_name, meta in TOOL_LIBRARY.items():
                enabled = 0 if (agent_id, tool_name) in defaults_disabled else 1
                conn.execute(
                    """
                    INSERT INTO Agent_Tool_Registry (agent_id, tool_name, is_enabled, description)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(agent_id, tool_name) DO NOTHING
                    """,
                    (agent_id, tool_name, enabled, meta["description"]),
                )
        conn.commit()
    finally:
        conn.close()


def get_registry_rows(agent_id: Optional[str] = None) -> List[dict]:
    query = "SELECT agent_id, tool_name, is_enabled, description, updated_at FROM Agent_Tool_Registry"
    params: tuple = ()
    if agent_id:
        query += " WHERE agent_id = ?"
        params = (agent_id,)
    query += " ORDER BY agent_id, tool_name"
    conn = get_db_connection()
    try:
        return [dict(r) for r in conn.execute(query, params).fetchall()]
    finally:
        conn.close()


def get_agent_tools(agent_id: str) -> List[str]:
    """Names of tools this agent is allowed to call (is_enabled = 1)."""
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT tool_name FROM Agent_Tool_Registry "
            "WHERE agent_id = ? AND is_enabled = 1 ORDER BY tool_name",
            (agent_id,),
        ).fetchall()
        return [r["tool_name"] for r in rows]
    finally:
        conn.close()


def set_agent_tool_enabled(
    agent_id: str,
    tool_name: str,
    enabled: bool,
    db_path: Optional[str] = None,
) -> dict:
    """Platform entry point for 'add/remove this tool for this agent'.

    Persists the gate in Agent_Tool_Registry, then re-syncs the live server
    so the change reaches tools/list immediately."""
    if tool_name not in TOOL_LIBRARY:
        raise ValueError(f"Unknown tool '{tool_name}'. Available: {sorted(TOOL_LIBRARY)}")
    if agent_id not in KNOWN_AGENT_IDS:
        raise ValueError(f"Unknown agent '{agent_id}'. Known: {list(KNOWN_AGENT_IDS)}")

    from datetime import datetime

    conn = get_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO Agent_Tool_Registry (agent_id, tool_name, is_enabled, description, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(agent_id, tool_name)
            DO UPDATE SET is_enabled = excluded.is_enabled, updated_at = excluded.updated_at
            """,
            (agent_id, tool_name, 1 if enabled else 0, TOOL_LIBRARY[tool_name]["description"],
             datetime.now().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    live_names = sync_server_from_registry()
    return {
        "agent_id": agent_id,
        "tool_name": tool_name,
        "enabled": enabled,
        "live_tools": sorted(live_names),
    }


# ==============================================================
# Live-server mutation
# ==============================================================

def register_tool(mcp_instance, name: str) -> bool:
    """Registers a library tool on the RUNNING server instance. Idempotent."""
    if name not in TOOL_LIBRARY:
        raise ValueError(f"Unknown tool '{name}'.")
    meta = TOOL_LIBRARY[name]
    try:
        mcp_instance.tool(name=name)(meta["fn"])
        return True
    except Exception:
        # Already present — treat as success.
        return False


def deregister_tool(mcp_instance, name: str) -> bool:
    """Removes a tool from the RUNNING server instance. Idempotent."""
    try:
        provider = getattr(mcp_instance, "local_provider", None)
        if provider is not None:
            provider.remove_tool(name)
        else:
            mcp_instance.remove_tool(name)
        return True
    except Exception:
        return False


async def list_live_tools(mcp_instance) -> List[str]:
    """Names currently served by the running instance (what clients see)."""
    tools = await mcp_instance.list_tools()
    return [t.name for t in tools]


def sync_server_from_registry(mcp_instance=None) -> List[str]:
    """
    Makes the live server agree with Agent_Tool_Registry:
    a tool stays registered iff at least one agent row enables it.
    Returns the resulting live tool-name list.
    """
    if mcp_instance is None:
        from mcp_server.server import mcp as mcp_instance

    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT tool_name, SUM(is_enabled) AS enabled_any "
            "FROM Agent_Tool_Registry GROUP BY tool_name"
        ).fetchall()
    finally:
        conn.close()

    should_be_live = {r["tool_name"] for r in rows if r["enabled_any"] and r["tool_name"] in TOOL_LIBRARY}

    for name in TOOL_LIBRARY:
        if name in should_be_live:
            register_tool(mcp_instance, name)
        else:
            # Not enabled for ANY agent -> gone from tools/list entirely.
            deregister_tool(mcp_instance, name)

    return sorted(should_be_live)


def bootstrap(mcp_instance=None) -> None:
    """Idempotent startup: seed registry defaults, then sync the live server."""
    seed_registry()
    sync_server_from_registry(mcp_instance=mcp_instance)

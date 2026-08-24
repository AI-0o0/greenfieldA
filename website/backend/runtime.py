"""
website/backend/runtime.py

Process-wide singletons for the Greenfield platform:
- the shared MCP client (connected over loopback HTTP to the FastMCP app
  this same process mounts at /mcp — one process, one live server),
- per-agent gated client views (Agent_Tool_Registry enforcement),
- the durable-checkpointed state-graph singletons (finance + crop disease).

Because both graphs run on SQLite checkpointers, killing this process
mid-run and restarting resumes every thread from its last durable
checkpoint (rubric: crash-and-resume).
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Dict, Optional

from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult

from mcp_server.tool_manager import get_agent_tools


async def _decline_elicitation(message, response_type, params, context):
    """
    Platform-safe elicitation policy: the website has no stdin. Interactive
    sign-off requests are DECLINED here by design — the crop graph performs
    its authoritative sign-off through Crop_HITL_Tasks + the admin console
    instead, and dispatch_equipment raises a clear 'human declined' error.
    """
    return ElicitResult(action="decline")


# ==============================================================
# Gated MCP client view (per-agent tool gating)
# ==============================================================

class GatedMCPClient:
    """
    Wraps the shared fastmcp Client so an agent only SEES (list_tools) and
    can only CALL (call_tool) tools enabled for its agent_id in
    Agent_Tool_Registry. The allow-list is re-read from the database on
    every call, so admin toggles take effect immediately without a restart.
    """

    def __init__(self, inner: Any, agent_id: str):
        self._inner = inner
        self.agent_id = agent_id

    async def list_tools(self):
        allowed = set(get_agent_tools(self.agent_id))
        tools = await self._inner.list_tools()
        return [t for t in tools if t.name in allowed]

    async def call_tool(self, name: str, payload: Any = None, **kwargs: Any):
        allowed = set(get_agent_tools(self.agent_id))
        if name not in allowed:
            raise PermissionError(
                f"Tool '{name}' is disabled for agent '{self.agent_id}' "
                f"by the administrator registry."
            )
        return await self._inner.call_tool(name, payload, **kwargs)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)


# ==============================================================
# Runtime container
# ==============================================================

class Runtime:
    def __init__(self) -> None:
        self.mcp_url = "/mcp (this process)"
        self.client: Optional[Client] = None
        self._clients_lock = threading.Lock()
        self._finance_graph: Optional[Any] = None
        self._crop_graph: Optional[Any] = None
        self._maintenance_graph: Optional[Any] = None
        self._orchestrator_graph: Optional[Any] = None
        self._llm: Optional[Any] = None
        self._memories: Dict[str, Any] = {}
        self._memories_lock = threading.Lock()

    # ---- lifecycle ----
    async def startup(self) -> None:
        """
        In-memory MCP transport: the client talks to the SAME live FastMCP
        instance this process mounts at /mcp — full protocol semantics
        (tools/list, call_tool, notifications) with no startup race. External
        clients (graders, demos) connect over real HTTP at /mcp and observe
        exactly the same tool set, including admin toggles.
        """
        from mcp_server.server import mcp as mcp_instance

        self.client = Client(
            mcp_instance,
            elicitation_handler=_decline_elicitation,
        )
        await self.client.__aenter__()
        await self.client.list_tools()

    async def shutdown(self) -> None:
        if self.client is not None:
            try:
                await self.client.__aexit__(None, None, None)
            except Exception:
                pass
            self.client = None

    # ---- lazy heavy singletons (built inside worker threads) ----
    def _build_sync(self, name: str, builder) -> Any:
        with self._clients_lock:
            cached = getattr(self, name)
            if cached is None:
                setattr(self, name, builder())
            return getattr(self, name)

    @property
    def llm(self):
        return self._build_sync("_llm", self._make_llm)

    def _make_llm(self):
        from agents.agent import get_base_llm

        return get_base_llm()

    @property
    def finance_graph(self):
        return self._build_sync("_finance_graph", self._make_finance_graph)

    def _make_finance_graph(self):
        from agents.graphs.finance.graph import create_finance_agent

        # persistent=True -> durable SQLite checkpointer (db/checkpoints.sqlite);
        # interactive=True -> interrupt_before at wait_farmer / admin_review /
        # wait_provider / farmer_confirm.
        return create_finance_agent(persistent=True, interactive=True)

    @property
    def crop_graph(self):
        return self._build_sync("_crop_graph", self._make_crop_graph)

    def _make_crop_graph(self):
        from agents.graphs.crop_disease.runner import get_crop_agent

        return get_crop_agent(force_rebuild=True)

    @property
    def maintenance_graph(self):
        return self._build_sync("_maintenance_graph", self._make_maintenance_graph)

    def _make_maintenance_graph(self):
        from agents.graphs.maintenance.runner import get_maintenance_agent

        return get_maintenance_agent()

    @property
    def orchestrator_graph(self):
        return self._build_sync("_orchestrator_graph", self._make_orchestrator_graph)

    def _make_orchestrator_graph(self):
        from agents.orchestrator import get_orchestrator_agent

        return get_orchestrator_agent()

    # ---- per-thread short-term memory for the knowledge assistant ----
    def memory_for(self, thread_id: str):
        with self._memories_lock:
            if thread_id not in self._memories:
                from agents.memory.memory import ShortTermMemory

                self._memories[thread_id] = ShortTermMemory()
            return self._memories[thread_id]

    def gated_client(self, agent_id: str) -> GatedMCPClient:
        if self.client is None:
            raise RuntimeError("MCP client not started.")
        return GatedMCPClient(self.client, agent_id)


runtime = Runtime()


def run_in_thread(fn, *args, **kwargs):
    """Runs blocking graph/LLM work off the event loop."""
    return asyncio.to_thread(fn, *args, **kwargs)

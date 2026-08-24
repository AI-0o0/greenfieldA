"""
website/backend/routers/threads.py

Inspection surface used for demo evidence: shows a thread's persisted
checkpoint state (what survived a process kill), where the graph is parked,
and any pending interrupt — without advancing the run.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException

from website.backend.runtime import runtime

router = APIRouter(prefix="/api/threads", tags=["threads"])


async def _crop_state(thread_id: str) -> dict:
    graph = await runtime.get_crop_graph()
    config = {"configurable": {"thread_id": thread_id}}
    snap = await graph.aget_state(config)
    values = dict(snap.values or {})
    interrupt = None
    for task in getattr(snap, "tasks", None) or []:
        for i in getattr(task, "interrupts", None) or ():
            interrupt = getattr(i, "value", i)
            break
    return {
        "agent_id": "crop_disease",
        "exists": bool(values),
        "next_nodes": list(snap.next or []),
        "pending_interrupt": interrupt,
        "values": values,
    }


def _finance_state(thread_id: str) -> dict:
    graph = runtime.finance_graph
    config = {"configurable": {"thread_id": thread_id}}
    snap = graph.get_state(config)
    values = dict(snap.values or {})
    # Trim bulky nested payloads for display.
    slim = {k: v for k, v in values.items() if k not in ("messages",)}
    slim = json.loads(json.dumps(slim, default=str))
    return {
        "agent_id": "finance",
        "exists": bool(values),
        "next_nodes": list(snap.next or []),
        "pending_interrupt": None,  # finance uses interrupt_before, visible via next_nodes
        "values": slim,
    }


def _maintenance_state(thread_id: str) -> dict:
    graph = runtime.maintenance_graph
    config = {"configurable": {"thread_id": thread_id}}
    snap = graph.get_state(config)
    values = dict(snap.values or {})
    interrupt = None
    for task in getattr(snap, "tasks", None) or []:
        for i in getattr(task, "interrupts", None) or ():
            interrupt = getattr(i, "value", i)
            break
    slim = {k: v for k, v in values.items() if k not in ("messages",)}
    return {
        "agent_id": "maintenance",
        "exists": bool(values),
        "next_nodes": list(snap.next or []),
        "pending_interrupt": interrupt,
        "values": slim,
    }


@router.get("/{thread_id}/state")
async def thread_state(thread_id: str):
    prefix = thread_id.split("-")[0].lower()
    if prefix.startswith("crop"):
        return await _crop_state(thread_id)
    if prefix.startswith("fin"):
        return await asyncio.to_thread(_finance_state, thread_id)
    if prefix.startswith("maint"):
        return await asyncio.to_thread(_maintenance_state, thread_id)
    return {
        "agent_id": prefix,
        "exists": True,
        "next_nodes": [],
        "pending_interrupt": None,
        "values": {},
    }


@router.get("/{agent_id}/{thread_id}")
async def thread_state_by_agent(agent_id: str, thread_id: str):
    if agent_id in ("crop_disease", "crop"):
        return await _crop_state(thread_id)
    if agent_id in ("finance", "fin"):
        return await asyncio.to_thread(_finance_state, thread_id)
    if agent_id in ("maintenance", "maint"):
        return await asyncio.to_thread(_maintenance_state, thread_id)
    if agent_id == "orchestrator":
        from website.backend.registry import _ORCHESTRATOR_ACTIVE_SPECIALIST
        active = _ORCHESTRATOR_ACTIVE_SPECIALIST.get(thread_id, "finance")
        if active == "crop_disease":
            return await _crop_state(thread_id)
        elif active == "maintenance":
            return await asyncio.to_thread(_maintenance_state, thread_id)
        else:
            return await asyncio.to_thread(_finance_state, thread_id)
    raise HTTPException(404, f"No checkpoint inspection for agent '{agent_id}'.")

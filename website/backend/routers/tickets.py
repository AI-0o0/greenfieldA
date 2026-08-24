"""
website/backend/routers/tickets.py

Admin surface: the failure/recovery ticket board (shared `Tickets` table,
written by BOTH state graphs on unplanned mid-node failures — a distinct
code path from HITL pauses). Resolving a ticket resumes the run from its
durable checkpoint; it never restarts from scratch.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.graphs.finance.tickets import (
    fetch_tickets,
    get_ticket,
    update_ticket_status,
)
from website.backend.runtime import runtime

router = APIRouter(prefix="/api/tickets", tags=["admin-tickets"])


class TicketStatusUpdate(BaseModel):
    notes: str = ""


class TicketResolve(BaseModel):
    notes: str = ""
    state_patch: dict | None = None


@router.get("")
async def list_tickets(status: Optional[str] = None):
    if status and status not in ("open", "investigating", "resolved"):
        raise HTTPException(400, "status must be open | investigating | resolved")
    rows = await asyncio.to_thread(fetch_tickets, status)
    return {"tickets": rows}


def _ticket_owner_graph(ticket: dict):
    """
    Routes the ticket to its owning graph (crop_disease, maintenance, or finance).
    """
    failed_node = str(ticket.get("failed_node") or "")
    thread_id = str(ticket.get("thread_id") or "")
    error_type = str(ticket.get("error_type") or "")

    if (
        "maint" in thread_id
        or error_type == "maintenance_execution_error"
        or failed_node in ("schedule_and_await_technician", "order_parts_and_await_delivery", "execute_maintenance", "await_operational_testing", "evaluate_testing")
    ):
        return "maintenance"

    from agents.graphs.crop_disease.nodes import _ERROR_SOURCES

    crop_nodes = {src for _, src in _ERROR_SOURCES}
    if failed_node in crop_nodes or "crop" in thread_id:
        return "crop_disease"
    return "finance"


@router.post("/{ticket_id}/investigate")
async def mark_investigating(ticket_id: int, body: TicketStatusUpdate):
    ticket = await asyncio.to_thread(get_ticket, ticket_id)
    if not ticket:
        raise HTTPException(404, f"Ticket #{ticket_id} not found.")
    await asyncio.to_thread(update_ticket_status, ticket_id, "investigating",
                            body.notes or None)
    return {"status": "investigating"}


@router.post("/{ticket_id}/resolve")
async def resolve_and_resume(ticket_id: int, body: TicketResolve):
    ticket = await asyncio.to_thread(get_ticket, ticket_id)
    if not ticket:
        raise HTTPException(404, f"Ticket #{ticket_id} not found.")
    if ticket["status"] == "resolved":
        raise HTTPException(400, f"Ticket #{ticket_id} is already resolved.")

    owner = _ticket_owner_graph(ticket)

    if owner == "maintenance":
        from agents.graphs.maintenance.runner import resolve_maintenance_ticket_and_resume

        summary = await asyncio.to_thread(
            resolve_maintenance_ticket_and_resume,
            ticket_id,
            body.notes or "Resolved by administrator",
            runtime.maintenance_graph,
            body.state_patch,
        )
        values = summary.get("values") or {}
        return {
            "status": "resumed",
            "owner": owner,
            "resumed_from_node": summary.get("resumed_from_node"),
            "paused": bool(summary.get("paused")),
            "paused_at": values.get("status"),
            "interrupt": summary.get("interrupt"),
            "trace": summary.get("trace", []),
        }

    if owner == "crop_disease":
        from agents.graphs.crop_disease.runner import resolve_crop_ticket_and_resume

        summary = await asyncio.to_thread(
            resolve_crop_ticket_and_resume,
            ticket_id,
            body.notes or "Resolved by administrator",
            runtime.crop_graph,
            body.state_patch,
        )
        values = summary.get("values") or {}
        return {
            "status": "resumed",
            "owner": owner,
            "resumed_from_node": summary.get("resumed_from_node"),
            "paused": bool(summary.get("paused")),
            "paused_at": values.get("status"),
            "interrupt": summary.get("interrupt"),
            "trace": summary.get("trace"),
        }

    from agents.graphs.finance.tickets import resolve_ticket_and_resume

    values = await asyncio.to_thread(
        resolve_ticket_and_resume,
        ticket_id,
        body.state_patch or {},
        body.notes or "Resolved by administrator",
        runtime.finance_graph,
    )
    snap_next = runtime.finance_graph.get_state(
        {"configurable": {"thread_id": ticket["thread_id"]}}
    ).next
    return {
        "status": "resumed",
        "owner": owner,
        "paused_at": list(snap_next) if snap_next else [],
        "trace": (values.get("execution_log") or [])[-8:] if isinstance(values, dict) else [],
    }

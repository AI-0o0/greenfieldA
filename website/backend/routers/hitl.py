"""
website/backend/routers/hitl.py

Admin surface: the HITL inbox. Unifies both escalation queues:
- HITL_Tasks        (finance graph, interrupt_before=admin_review)
- Crop_HITL_Tasks   (crop disease graph, mid-node interrupt in hitl_check)

Acting on a task through THIS api (driven by the platform UI) is what makes
the paused run resume — there is no auto-approve anywhere.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mcp_server.tools import get_db_connection
from agents.graphs.crop_disease.runner import list_crop_hitl_tasks, get_crop_hitl_task
from agents.graphs.finance.hitl import fetch_pending_hitl_tasks, get_hitl_task
from website.backend.runtime import runtime

router = APIRouter(prefix="/api/hitl", tags=["admin-hitl"])


class HitlDecision(BaseModel):
    decision: str  # approve | reject | more_info
    notes: str = ""


def _safe_snapshot(raw: Optional[str]) -> Any:
    try:
        return json.loads(raw) if raw else None
    except Exception:
        return raw


@router.get("")
async def list_tasks(status: Optional[str] = None):
    def _collect() -> List[Dict[str, Any]]:
        tasks: List[Dict[str, Any]] = []

        conn = get_db_connection()
        try:
            query = (
                "SELECT t.*, c.company_name FROM HITL_Tasks t "
                "LEFT JOIN Financing_Applications f ON t.application_id = f.application_id "
                "LEFT JOIN Customers c ON f.customer_id = c.customer_id"
            )
            params: tuple = ()
            if status:
                query += " WHERE t.status = ?"
                params = (status,)
            query += " ORDER BY t.task_id DESC"
            for r in conn.execute(query, params).fetchall():
                row = dict(r)
                reason_lower = (row.get("reason") or "").lower()
                if row.get("node_name") == "hitl_cost_approval" and "loan" not in reason_lower and "finance" not in reason_lower:
                    row["kind"] = "maintenance"
                else:
                    row["kind"] = "finance"
                row["state_snapshot_parsed"] = _safe_snapshot(row.pop("state_snapshot", None))
                tasks.append(row)
        finally:
            conn.close()

        for row in list_crop_hitl_tasks(status=status or "pending"):
            row["kind"] = "crop_disease"
            row["state_snapshot_parsed"] = _safe_snapshot(row.pop("state_snapshot", None))
            tasks.append(row)

        tasks.sort(key=lambda t: t.get("task_id") or 0, reverse=True)
        return tasks

    return {"tasks": await asyncio.to_thread(_collect)}


@router.get("/{kind}/{task_id}")
async def task_detail(kind: str, task_id: int):
    if kind in ("finance", "maintenance"):
        row = await asyncio.to_thread(get_hitl_task, task_id)
    elif kind == "crop_disease":
        row = await asyncio.to_thread(get_crop_hitl_task, task_id)
    else:
        raise HTTPException(400, f"Unknown kind '{kind}' (use finance | crop_disease | maintenance).")
    if not row:
        raise HTTPException(404, f"HITL task #{task_id} not found.")
    row["kind"] = kind
    row["state_snapshot_parsed"] = _safe_snapshot(row.pop("state_snapshot", None))
    return {"task": row}


@router.post("/{kind}/{task_id}/resolve")
async def resolve_task(kind: str, task_id: int, decision: HitlDecision):
    if decision.decision not in ("approve", "reject", "more_info"):
        raise HTTPException(400, "decision must be approve | reject | more_info")

    from agents.graphs.finance.hitl import get_hitl_task
    from website.backend.registry import _ORCHESTRATOR_ACTIVE_SPECIALIST

    task = await asyncio.to_thread(get_hitl_task, task_id)
    node_name = task.get("node_name") if task else ""
    reason = (task.get("reason") or "").lower() if task else ""
    thread_id = task.get("thread_id") if task else ""
    active_spec = _ORCHESTRATOR_ACTIVE_SPECIALIST.get(thread_id, "")

    is_finance_task = (
        kind == "finance"
        or node_name == "admin_review"
        or "loan" in reason
        or "finance" in reason
        or "capital exposure" in reason
        or active_spec == "finance"
    )

    if is_finance_task and kind != "crop_disease":
        from agents.graphs.finance.hitl import resume_hitl_task

        try:
            result = await asyncio.to_thread(
                resume_hitl_task,
                task_id,
                decision.decision,
                decision.notes,
                runtime.finance_graph,
            )
        except ValueError as exc:
            raise HTTPException(404, str(exc))

        values = dict(result or {})
        snap_config = {"configurable": {"thread_id": values.get("thread_id", "")}}
        snap_next = runtime.finance_graph.get_state(snap_config).next
        if snap_next and snap_next[0] == "wait_provider":
            from agents.graphs.finance.graph import run_finance_turn
            run_finance_turn(runtime.finance_graph, values.get("thread_id", ""), {"provider_response": "approved"})
            snap_next = runtime.finance_graph.get_state(snap_config).next

        return {
            "status": "resumed",
            "decision": decision.decision,
            "paused_at": list(snap_next) if snap_next else [],
            "trace": (values.get("execution_log") or [])[-8:],
        }

    if kind == "maintenance":
        from agents.graphs.maintenance.runner import resume_maintenance_interrupt

        if not task:
            raise HTTPException(404, f"HITL task #{task_id} not found.")

        approved = decision.decision == "approve"
        summary = await asyncio.to_thread(
            resume_maintenance_interrupt,
            runtime.maintenance_graph,
            task["thread_id"],
            {"approved": approved, "notes": decision.notes},
        )
        values = summary.get("values") or {}
        return {
            "status": "resumed",
            "decision": decision.decision,
            "paused_at": values.get("status"),
            "paused": bool(summary.get("paused")),
            "interrupt": summary.get("interrupt"),
            "trace": summary.get("trace", []),
        }

    if kind == "crop_disease":
        if decision.decision == "more_info":
            raise HTTPException(
                400,
                "Crop sign-off pauses support approve/reject only "
                "(reject sends the proposal back for revision).",
            )
        from agents.graphs.crop_disease.runner import resume_crop_interrupt

        task = await asyncio.to_thread(get_crop_hitl_task, task_id)
        if not task:
            raise HTTPException(404, f"HITL task #{task_id} not found.")

        approved = decision.decision == "approve"
        summary = await asyncio.to_thread(
            resume_crop_interrupt,
            runtime.crop_graph,
            task["thread_id"],
            {"approved": approved, "notes": decision.notes},
        )
        values = summary.get("values") or {}
        return {
            "status": "resumed",
            "decision": decision.decision,
            "paused_at": values.get("status"),
            "paused": bool(summary.get("paused")),
            "interrupt": summary.get("interrupt"),
        }

    raise HTTPException(400, f"Unknown kind '{kind}'.")

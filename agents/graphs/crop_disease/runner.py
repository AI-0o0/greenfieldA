"""
agents/graphs/crop_disease/runner.py

Turn-based invocation seam between the platform (website/backend) and the
Crop Disease Treatment state graph. Mirrors the role that
agents/graphs/finance/graph.py::run_finance_turn plays for the finance graph.

Concerns located here (rubric pointers):
- Checkpointed invocation:      run_crop_turn()
- Interrupt resume (HITL and
  farmer/observation pauses):   resume_crop_interrupt()  -> Command(resume=...)
- Failure-ticket recovery:      resolve_crop_ticket_and_resume()
  (LangGraph time-travel: update_state(as_node=...) + invoke(None), so the run
  re-enters at the failed stage from its durable checkpoint instead of
  restarting from the top.)
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from mcp_server.tools import get_db_connection


# ==============================================================
# Case-row bootstrap (nodes UPDATE Crop_Cases WHERE case_id=?,
# so a row must exist before the first turn of a thread)
# ==============================================================

def ensure_case_row(
    thread_id: str,
    customer_id: int,
    field_id: int,
) -> int:
    """Inserts the Crop_Cases row for a fresh thread if missing; returns case_id."""
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO Crop_Cases (thread_id, customer_id, field_id) "
            "VALUES (?, ?, ?)",
            (thread_id, customer_id, field_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT case_id FROM Crop_Cases WHERE thread_id = ?", (thread_id,)
        ).fetchone()
        return row["case_id"]
    finally:
        conn.close()


# ==============================================================
# Graph instance management (one durable-SQLite graph per process)
# ==============================================================

_GRAPH_CACHE: Dict[str, Any] = {}


def get_crop_agent(db_path: Optional[str] = None, force_rebuild: bool = False):
    """
    Returns the process-wide crop-disease graph backed by the durable SQLite
    checkpointer (db/farm.db by default). Because the checkpointer is durable,
    the platform process can be killed mid-run and a restarted process resumes
    every thread from its last checkpoint.
    """
    key = db_path or "default"
    if force_rebuild or key not in _GRAPH_CACHE:
        from agents.graphs.crop_disease.graph import build_crop_disease_graph

        _GRAPH_CACHE[key] = build_crop_disease_graph(db_path=db_path)
    return _GRAPH_CACHE[key]


# ==============================================================
# Interrupt extraction helpers
# ==============================================================

def _extract_interrupt(graph: Any, config: dict, result: Any) -> Optional[dict]:
    """Pulls the pending interrupt payload out of an invoke result / state."""
    intr = None
    if isinstance(result, dict):
        pending = result.get("__interrupt__")
        if pending:
            first = pending[0] if isinstance(pending, (list, tuple)) else pending
            intr = getattr(first, "value", first)
    if intr is None:
        snap = graph.get_state(config)
        for task in getattr(snap, "tasks", None) or []:
            for i in getattr(task, "interrupts", None) or ():
                intr = getattr(i, "value", i)
                break
            if intr is not None:
                break
    return intr


def get_pending_interrupt(graph: Any, config: dict) -> Optional[dict]:
    """Returns the payload of the interrupt this thread is parked on, if any."""
    return _extract_interrupt(graph, config, None)


def summarize_turn(graph: Any, config: dict, result: Any) -> dict:
    """Uniform turn summary consumed by the platform's chat/HITL surfaces."""
    values = dict(result) if isinstance(result, dict) else {}
    interrupt_payload = _extract_interrupt(graph, config, result)

    # A HITL pause is only surfaced as "awaiting admin" while its task row
    # is still pending; farmer/observation waits are external replies.
    paused = interrupt_payload is not None
    return {
        "ok": True,
        "paused": paused,
        "status": values.get("status"),
        "case_id": values.get("case_id"),
        "ticket_id": values.get("ticket_id"),
        "hitl_task_id": values.get("hitl_task_id"),
        "interrupt": interrupt_payload,
        "values": values,
    }


# ==============================================================
# Turn entry point
# ==============================================================

def _invoke_graph(graph: Any, payload: Any, config: dict) -> Any:
    import asyncio
    import concurrent.futures

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, graph.ainvoke(payload, config=config)).result()
    else:
        return asyncio.run(graph.ainvoke(payload, config=config))


def run_crop_turn(
    graph: Any,
    thread_id: str,
    report: str,
    customer_id: int,
    field_id: int,
) -> dict:
    """
    Starts (or continues, post-resume) a crop-disease case on this thread.
    The initial payload seeds ownership FKs and the farmer's symptom report;
    everything after that lives in the durable checkpoint.
    """
    config = {"configurable": {"thread_id": thread_id}}
    case_id = ensure_case_row(thread_id=thread_id, customer_id=customer_id, field_id=field_id)

    input_payload = {
        "case_id": case_id,
        "thread_id": thread_id,
        "customer_id": customer_id,
        "field_id": field_id,
        "retry_count": 0,
        "messages": [HumanMessage(content=report)],
    }
    result = _invoke_graph(graph, input_payload, config=config)
    return summarize_turn(graph, config, result)


def resume_crop_interrupt(
    graph: Any,
    thread_id: str,
    resume_payload: Dict[str, Any],
) -> dict:
    """
    Resumes a thread parked on interrupt() (chemical sign-off, farmer
    confirmation, or observation report). `resume_payload` shape depends on
    which node interrupted — see the interrupt payloads in nodes.py:
      hitl_check:               {"approved": bool, "notes": str}
      await_farmer_confirmation: {"confirmed": bool}
      await_observation:        {"outcome": recovered|improved|worsened, "notes": str}
    """
    config = {"configurable": {"thread_id": thread_id}}
    result = _invoke_graph(graph, Command(resume=resume_payload), config=config)
    return summarize_turn(graph, config, result)


# ==============================================================
# Failure-ticket recovery (distinct code path from HITL resume)
# ==============================================================

def _strip_error_markers(field: Optional[dict]) -> Optional[dict]:
    if not isinstance(field, dict):
        return field
    cleaned = {k: v for k, v in field.items() if k not in ("error", "error_detail")}
    return cleaned


def resolve_crop_ticket_and_resume(
    ticket_id: int,
    resolution_notes: str = "",
    graph: Any = None,
    state_patch: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
) -> dict:
    """
    Resolves an open failure ticket and resumes the run from its durable
    checkpoint. LangGraph time-travel positions the graph as if the failed
    stage just completed (update_state with as_node), so completed nodes are
    NOT re-executed — then invoke(None) follows the graph edges onward.

    Re-entry mapping:
      diagnose                                -> re-routes into diagnose (retry budget reset)
      propose_treatment_or_execute_treatment  -> re-propose (or re-dispatch when the
                                                 failure happened at dispatch time)
      evaluate_result                         -> re-evaluates a corrected observation
                                                 (supply outcome via state_patch)
    """
    conn = get_db_connection()
    try:
        ticket = conn.execute(
            "SELECT * FROM Tickets WHERE ticket_id = ?", (ticket_id,)
        ).fetchone()
        if not ticket:
            raise ValueError(f"Ticket #{ticket_id} not found.")

        from datetime import datetime

        conn.execute(
            "UPDATE Tickets SET status = 'resolved', resolution_notes = ?, "
            "resolved_at = ? WHERE ticket_id = ?",
            (
                resolution_notes or "Resolved by administrator",
                datetime.now().isoformat(),
                ticket_id,
            ),
        )
        conn.commit()
        failed_node = ticket["failed_node"]
        snapshot = json.loads(ticket["state_snapshot"] or "{}")
    finally:
        conn.close()

    if graph is None:
        graph = get_crop_agent(db_path=db_path)
    config = {"configurable": {"thread_id": ticket["thread_id"]}}

    error_marker = ""
    pt = snapshot.get("proposed_treatment") or {}
    ob = snapshot.get("observation_result") or {}
    dg = snapshot.get("diagnosis") or {}
    for d in (pt, ob, dg):
        if isinstance(d, dict) and d.get("error"):
            error_marker = d["error"]
            break

    patch: Dict[str, Any] = {}
    if failed_node == "diagnose":
        as_node = "diagnose"          # conditional edge loops back into diagnose
        patch["retry_count"] = 0      # restore retry budget
        patch["diagnosis"] = {**dg, "error": None} if dg else None
    elif failed_node == "propose_treatment_or_execute_treatment":
        dispatch_stage = error_marker in (
            "dispatch_failed",
            "attempted_execution_without_hitl_approval",
        )
        if dispatch_stage:
            as_node = "await_farmer_confirmation"  # routes back to execute_treatment
        else:
            as_node = "diagnose"                   # diagnosis still grounded -> re-propose
        patch["proposed_treatment"] = _strip_error_markers(pt)
    elif failed_node == "evaluate_result":
        as_node = "await_observation"  # unconditional edge -> evaluate_result
        patch["observation_result"] = _strip_error_markers(ob)
    else:
        as_node = "diagnose"
        patch["retry_count"] = 0

    if state_patch:
        patch.update(state_patch)
    patch = {k: v for k, v in patch.items() if v is not None}

    if patch:
        graph.update_state(config, patch, as_node=as_node)
    else:
        graph.update_state(config, {}, as_node=as_node)

    result = graph.invoke(None, config=config)
    summary = summarize_turn(graph, config, result)
    summary["resolved_ticket_id"] = ticket_id
    summary["resumed_from_node"] = as_node
    return summary


# ==============================================================
# Crop_HITL_Tasks helpers used by the platform's unified HITL inbox
# ==============================================================

def list_crop_hitl_tasks(status: Optional[str] = None) -> list[dict]:
    query = "SELECT * FROM Crop_HITL_Tasks"
    params: tuple = ()
    if status:
        query += " WHERE status = ?"
        params = (status,)
    query += " ORDER BY task_id DESC"
    conn = get_db_connection()
    try:
        return [dict(r) for r in conn.execute(query, params).fetchall()]
    finally:
        conn.close()


def get_crop_hitl_task(task_id: int) -> Optional[dict]:
    conn = get_db_connection()
    try:
        row = conn.execute(
            "SELECT * FROM Crop_HITL_Tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def new_thread_id(prefix: str = "crop") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"

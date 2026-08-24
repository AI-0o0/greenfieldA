"""
agents/graphs/maintenance/runner.py

Turn-based invocation seam between the platform (website/backend) and the
Equipment Maintenance & Repair state graph.

Concerns located here:
- Checkpointed invocation:      run_maintenance_turn()
- Interrupt resume (HITL,
  technician, parts, testing):   resume_maintenance_interrupt() -> Command(resume=...)
- Failure-ticket recovery:      resolve_maintenance_ticket_and_resume()
  (LangGraph time-travel: update_state(as_node=...) + invoke(None))
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from mcp_server.tools import get_db_connection

_GRAPH_CACHE: Dict[str, Any] = {}


def get_maintenance_agent(db_path: Optional[str] = None):
    """
    Returns the process-wide maintenance graph backed by the durable SQLite
    checkpointer (db/farm.db by default).
    """
    key = db_path or "default"
    if key not in _GRAPH_CACHE:
        from agents.graphs.maintenance.graph import build_maintenance_graph

        _GRAPH_CACHE[key] = build_maintenance_graph(db_path=db_path)
    return _GRAPH_CACHE[key]


def _extract_interrupt(graph: Any, config: dict, result: Any) -> Optional[dict]:
    """Extracts pending interrupt payload from invoke result or graph state."""
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
    """Uniform turn summary consumed by the platform's chat and admin surfaces."""
    values = dict(result) if isinstance(result, dict) else {}
    interrupt_payload = _extract_interrupt(graph, config, result)
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
        "trace": values.get("execution_log", []),
    }


def run_maintenance_turn(
    graph: Any,
    thread_id: str,
    issue_report: str,
    equipment_id: int = 3,
    customer_id: int = 1,
) -> dict:
    """
    Starts or continues a maintenance case on this thread.
    Seeds equipment identity and malfunction report; state is persisted in SQLite.
    """
    config = {"configurable": {"thread_id": thread_id}}

    input_payload = {
        "thread_id": thread_id,
        "customer_id": customer_id,
        "equipment_id": equipment_id,
        "issue_description": issue_report,
        "retry_count": 0,
        "messages": [HumanMessage(content=issue_report)],
    }
    result = graph.invoke(input_payload, config=config)
    return summarize_turn(graph, config, result)


def resume_maintenance_interrupt(
    graph: Any,
    thread_id: str,
    resume_payload: Dict[str, Any],
) -> dict:
    """
    Resumes a maintenance thread parked on interrupt() (cost approval,
    technician arrival, parts delivery, or operational test).
    """
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(Command(resume=resume_payload), config=config)
    return summarize_turn(graph, config, result)


def resolve_maintenance_ticket_and_resume(
    ticket_id: int,
    resolution_notes: str = "",
    graph: Any = None,
    state_patch: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
) -> dict:
    """
    Resolves an open maintenance failure ticket and resumes the run from its
    durable checkpoint using LangGraph time-travel (update_state as_node).
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
        graph = get_maintenance_agent(db_path=db_path)
    config = {"configurable": {"thread_id": ticket["thread_id"]}}

    # Determine safe re-entry node
    if failed_node == "order_parts_and_await_delivery":
        as_node = "schedule_and_await_technician"
    elif failed_node == "schedule_and_await_technician":
        as_node = "hitl_cost_approval"
    elif failed_node == "evaluate_testing":
        as_node = "execute_maintenance"
    else:
        as_node = "diagnose_from_manuals"

    patch: Dict[str, Any] = {
        "status": "resumed_from_ticket",
        "simulated_error_node": None,
        "simulated_error_message": None,
    }
    if state_patch:
        patch.update(state_patch)

    graph.update_state(config, patch, as_node=as_node)
    result = graph.invoke(None, config=config)
    summary = summarize_turn(graph, config, result)
    summary["resolved_ticket_id"] = ticket_id
    summary["resumed_from_node"] = as_node
    return summary


def new_thread_id(prefix: str = "maint") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"

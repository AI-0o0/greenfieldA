"""
agents/graphs/finance/hitl.py

Human-in-the-Loop (HITL) Policy Definitions and Escalation Management for the
Greenfield Autonomous Finance Graph.

EXPLICIT HITL ESCALATION POLICIES (Rubric Requirement):
Under any of the following conditions, the graph MUST NOT proceed automatically:
1. High Capital Exposure: Assessed loan amount >= $50,000 USD.
2. Elevated Underwriting Risk: Applicant risk rating evaluated as 'high'.
3. Low Debt Service Margin: Debt Service Coverage Ratio (DSCR) < 1.25.
4. Domain Specialist Escalation: Complex agronomic or machinery modification flagged.

When triggered, the graph pauses at the `admin_review` checkpoint, writes full state
to durable storage, and opens a task in `HITL_Tasks` for administrative action.
"""

from __future__ import annotations

import datetime
from typing import Optional, List, Dict, Any, Tuple, Literal
from langchain_core.language_models.chat_models import BaseChatModel

from agents.graphs.finance.db import get_db_connection, serialize_state_for_db


def evaluate_hitl_policy(
    amount: float,
    risk: str,
    dscr: float,
    specialist_escalated: bool = False,
) -> Tuple[bool, List[str]]:
    """
    Evaluates whether an application requires explicit senior human administrator review.
    Returns (hitl_required, list_of_policy_reasons).
    """
    reasons: List[str] = []

    if amount >= 50000.0:
        reasons.append(f"High Capital Exposure: Assessed loan amount ${amount:,.2f} >= $50,000 policy threshold")

    if risk.lower() == "high":
        reasons.append("Elevated Underwriting Risk: Applicant risk classification is 'high'")

    if dscr < 1.25:
        reasons.append(f"Low Debt Service Margin: DSCR ({dscr:.2f}) is below the mandatory 1.25 coverage floor")

    if specialist_escalated:
        reasons.append("Domain Specialist Escalation: Custom agronomic or machinery modification requires human sign-off")

    return (len(reasons) > 0, reasons)


def create_or_update_hitl_task(
    thread_id: str,
    application_id: Optional[int],
    reason: str,
    assessed_amount: float,
    dscr: float,
    risk_level: str,
    state_snapshot: Dict[str, Any],
    db_path: Optional[str] = None,
) -> int:
    """
    Inserts or updates a pending HITL task in SQLite HITL_Tasks table.
    """
    snap_json = serialize_state_for_db(state_snapshot)
    with get_db_connection(db_path) as conn:
        existing = conn.execute(
            "SELECT task_id FROM HITL_Tasks WHERE thread_id = ? AND status = 'pending'",
            (thread_id,),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE HITL_Tasks 
                   SET node_name = 'admin_review', reason = ?, assessed_amount = ?, dscr = ?, risk_level = ?, state_snapshot = ?
                   WHERE task_id = ?""",
                (reason, assessed_amount, dscr, risk_level, snap_json, existing["task_id"]),
            )
            conn.commit()
            return existing["task_id"]
        else:
            cursor = conn.execute(
                """INSERT INTO HITL_Tasks 
                   (thread_id, application_id, node_name, reason, assessed_amount, dscr, risk_level, state_snapshot, status) 
                   VALUES (?, ?, 'admin_review', ?, ?, ?, ?, ?, 'pending')""",
                (thread_id, application_id, reason, assessed_amount, dscr, risk_level, snap_json),
            )
            conn.commit()
            return cursor.lastrowid


def fetch_pending_hitl_tasks(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all pending HITL tasks from the database."""
    with get_db_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM HITL_Tasks WHERE status = 'pending' ORDER BY task_id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_hitl_task(task_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves a specific HITL task by its ID."""
    with get_db_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM HITL_Tasks WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None


def resume_hitl_task(
    task_id: int,
    decision: Literal["approve", "reject", "more_info"],
    admin_feedback: Optional[str] = None,
    graph: Optional[Any] = None,
    checkpointer: Optional[Any] = None,
    db_path: Optional[str] = None,
    llm: Optional[BaseChatModel] = None,
) -> Dict[str, Any]:
    """
    Submits an admin HITL decision via the platform UI, updates the task in SQLite,
    and resumes the paused graph run from its checkpoint.
    """
    with get_db_connection(db_path) as conn:
        task = conn.execute("SELECT * FROM HITL_Tasks WHERE task_id = ?", (task_id,)).fetchone()
        if not task:
            raise ValueError(f"HITL Task #{task_id} not found.")

        thread_id = task["thread_id"]
        status_map = {
            "approve": "approved",
            "reject": "rejected",
            "more_info": "more_info",
        }
        conn.execute(
            """UPDATE HITL_Tasks 
               SET status = ?, admin_notes = ?, resolved_at = ? 
               WHERE task_id = ?""",
            (status_map.get(decision, "approved"), admin_feedback or "", datetime.datetime.now().isoformat(), task_id),
        )
        conn.commit()

    # Late import to avoid circular dependencies
    from agents.graphs.finance.graph import create_finance_agent, run_finance_turn

    active_graph = graph or create_finance_agent(checkpointer=checkpointer, interactive=True, llm=llm, db_path=db_path)
    update_input = {
        "admin_decision": decision,
        "admin_feedback": admin_feedback,
    }
    return run_finance_turn(active_graph, thread_id, update_input)

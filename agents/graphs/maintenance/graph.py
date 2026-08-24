"""
agents/graphs/maintenance/graph.py

Graph assembly and compilation for the Equipment Maintenance & Repair State Graph.
Connects all diagnostic, decomposition, HITL, waiting, and recovery nodes,
backed by a durable SQLite checkpointer (db/farm.db).
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Optional

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from agents.graphs.maintenance.nodes import (
    await_operational_testing,
    close_case,
    collect_maintenance_request,
    decompose_maintenance_workflow,
    diagnose_from_manuals,
    estimate_cost_and_check_hitl,
    evaluate_testing,
    execute_maintenance,
    handle_failure,
    hitl_cost_approval,
    order_parts_and_await_delivery,
    route_after_evaluate_testing,
    route_after_hitl_approval,
    schedule_and_await_technician,
)
from agents.graphs.maintenance.state import MaintenanceState


def build_maintenance_graph(
    checkpointer: Optional[Any] = None,
    db_path: Optional[str] = None,
):
    """
    Assembles and compiles the Equipment Maintenance & Repair State Graph.
    Uses durable SQLite checkpointer for persistence across process crashes.
    """
    builder = StateGraph(MaintenanceState)

    # 1. Register Nodes
    builder.add_node("collect_maintenance_request", collect_maintenance_request)
    builder.add_node("diagnose_from_manuals", diagnose_from_manuals)
    builder.add_node("decompose_maintenance_workflow", decompose_maintenance_workflow)
    builder.add_node("estimate_cost_and_check_hitl", estimate_cost_and_check_hitl)
    builder.add_node("hitl_cost_approval", hitl_cost_approval)
    builder.add_node("schedule_and_await_technician", schedule_and_await_technician)
    builder.add_node("order_parts_and_await_delivery", order_parts_and_await_delivery)
    builder.add_node("execute_maintenance", execute_maintenance)
    builder.add_node("await_operational_testing", await_operational_testing)
    builder.add_node("evaluate_testing", evaluate_testing)
    builder.add_node("handle_failure", handle_failure)
    builder.add_node("close_case", close_case)

    # 2. Sequential Edges
    builder.add_edge(START, "collect_maintenance_request")
    builder.add_edge("collect_maintenance_request", "diagnose_from_manuals")
    builder.add_edge("diagnose_from_manuals", "decompose_maintenance_workflow")
    builder.add_edge("decompose_maintenance_workflow", "estimate_cost_and_check_hitl")
    builder.add_edge("estimate_cost_and_check_hitl", "hitl_cost_approval")

    # 3. Conditional Edge after HITL Cost Approval
    builder.add_conditional_edges(
        "hitl_cost_approval",
        route_after_hitl_approval,
        {
            "schedule_and_await_technician": "schedule_and_await_technician",
            "close_case": "close_case",
        },
    )

    # 4. Sequential Logistics & Execution Chain
    builder.add_edge("schedule_and_await_technician", "order_parts_and_await_delivery")
    builder.add_edge("order_parts_and_await_delivery", "execute_maintenance")
    builder.add_edge("execute_maintenance", "await_operational_testing")
    builder.add_edge("await_operational_testing", "evaluate_testing")

    # 5. Conditional Edge after Testing Evaluation
    builder.add_conditional_edges(
        "evaluate_testing",
        route_after_evaluate_testing,
        {
            "close_case": "close_case",
            "diagnose_from_manuals": "diagnose_from_manuals",
            "handle_failure": "handle_failure",
        },
    )

    # 6. Terminal Edges
    builder.add_edge("close_case", END)
    builder.add_edge("handle_failure", END)

    # Checkpointer configuration
    if checkpointer is not None:
        cp = checkpointer
    else:
        db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "db"))
        os.makedirs(db_dir, exist_ok=True)
        target_db_path = db_path or os.environ.get("GREENFIELD_DB_PATH") or os.path.join(db_dir, "farm.db")
        conn = sqlite3.connect(target_db_path, check_same_thread=False)
        cp = SqliteSaver(conn)

    return builder.compile(checkpointer=cp)

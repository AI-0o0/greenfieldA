"""
tests/test_maintenance_agent.py

Comprehensive Unit & Integration Test Suite for Equipment Maintenance & Repair State Graph.
Tests Task Decomposition, Manuals RAG, >$500 HITL Cost Approval, Multi-day Wait Interrupts,
Unplanned Failure Ticketing, and SQLite Durable Crash-and-Resume.
"""

import asyncio
import json
import sqlite3
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from mcp_server.tools import get_db_connection
from agents.graphs.maintenance import (
    MaintenanceState,
    collect_maintenance_request,
    diagnose_from_manuals,
    decompose_maintenance_workflow,
    estimate_cost_and_check_hitl,
    hitl_cost_approval,
    schedule_and_await_technician,
    order_parts_and_await_delivery,
    execute_maintenance,
    await_operational_testing,
    evaluate_testing,
    handle_failure,
    close_case,
    COST_HITL_THRESHOLD,
    build_maintenance_graph,
    run_maintenance_turn,
    resume_maintenance_interrupt,
    resolve_maintenance_ticket_and_resume,
)


@pytest.fixture(autouse=True)
def setup_test_db():
    """Seeds test equipment and technicians in SQLite database."""
    with get_db_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO Customers (customer_id, company_name, credit_hold) VALUES (1, 'Nile Delta Farms', 0)")
        conn.execute("INSERT OR IGNORE INTO Equipment (equipment_id, serial_number, equipment_type, status, current_location) VALUES (3, 'SPR-3001', 'sprayer', 'idle', 'Depot A')")
        conn.execute("INSERT OR IGNORE INTO Technicians (technician_id, full_name, role, authenticated) VALUES (1, 'Mona Adel', 'technician', 1)")
        conn.execute("UPDATE Equipment SET status = 'idle' WHERE equipment_id = 3")
        conn.commit()


def create_initial_state(
    issue: str = "Sprayer SPR-3001 hydraulic main pump leaking and pressure dropping rapidly.",
    thread_id: str = "test_maint_thread_100",
) -> MaintenanceState:
    return {
        "case_id": 100,
        "thread_id": thread_id,
        "customer_id": 1,
        "equipment_id": 3,
        "serial_number": "SPR-3001",
        "equipment_type": "sprayer",
        "issue_description": issue,
        "status": "request_collected",
        "messages": [HumanMessage(content=issue)],
        "retry_count": 0,
        "execution_log": [],
    }


# ==============================================================
# 1. Individual Node Tests
# ==============================================================

def test_collect_maintenance_request_node():
    state = create_initial_state(issue="Tractor TRC-2001 transmission slipping")
    updates = collect_maintenance_request(state)
    assert updates["status"] == "request_collected"
    assert "SPR-3001" in updates["serial_number"] or "TRC" in state["issue_description"]
    assert len(updates["execution_log"]) > 0


@patch("agents.graphs.maintenance.nodes._query_manuals_rag")
def test_diagnose_from_manuals_rag_addition(mock_rag):
    mock_rag.return_value = "SPR-3001 Manual: Hydraulic pump failure requires HP-400 pump replacement."
    state = create_initial_state(issue="Hydraulic line pressure dropped and fluid leaking")
    updates = diagnose_from_manuals(state)

    assert updates["status"] == "diagnosed"
    assert "hydraulic" in updates["diagnosis"]["root_cause"].lower()
    assert len(updates["diagnosis"]["parts"]) > 0
    assert updates["rag_context"] == mock_rag.return_value


def test_decompose_maintenance_workflow_addition():
    state = create_initial_state()
    state["diagnosis"] = {
        "root_cause": "Hydraulic seal rupture",
        "estimated_labor_hours": 4.0,
        "parts": [{"part_name": "Hydraulic Pump Assembly", "unit_price": 750.0}],
    }
    updates = decompose_maintenance_workflow(state)

    assert updates["status"] == "plan_decomposed"
    plan = updates["maintenance_plan"]
    assert len(plan) == 4
    assert plan[0]["title"] == "On-Site Physical Inspection & Teardown"
    assert plan[1]["title"] == "Spare Parts Procurement & Delivery"
    assert plan[2]["title"] == "Component Installation & Torque Calibration"
    assert plan[3]["title"] == "Operational Load Testing & Sign-off"


def test_estimate_cost_and_hitl_threshold_check():
    # Test High Cost > $500 -> HITL Required
    state_high = create_initial_state()
    state_high["diagnosis"] = {
        "estimated_labor_hours": 4.5,
        "parts": [{"part_name": "Hydraulic Pump", "unit_price": 750.0, "qty": 1}],
    }
    updates_high = estimate_cost_and_check_hitl(state_high)
    assert updates_high["total_cost"] == 750.0 + (4.5 * 60.0)  # $1,020
    assert updates_high["hitl_required"] is True

    # Test Low Cost < $500 -> No HITL
    state_low = create_initial_state()
    state_low["diagnosis"] = {
        "estimated_labor_hours": 1.5,
        "parts": [{"part_name": "Nozzle Tips", "unit_price": 120.0, "qty": 1}],
    }
    updates_low = estimate_cost_and_check_hitl(state_low)
    assert updates_low["total_cost"] == 120.0 + (1.5 * 60.0)  # $210
    assert updates_low["hitl_required"] is False


@patch("agents.graphs.maintenance.nodes.interrupt")
def test_hitl_cost_approval_flow(mock_interrupt):
    mock_interrupt.return_value = {"approved": True, "notes": "Approved by senior asset manager"}

    state = create_initial_state(thread_id="test_hitl_maint_1")
    state["hitl_required"] = True
    state["total_cost"] = 950.0
    state["parts_needed"] = [{"part_name": "Pump Assembly", "unit_price": 750.0}]

    updates = hitl_cost_approval(state)
    assert updates["status"] == "cost_approved"
    assert updates["hitl_status"] == "approved"
    assert updates["hitl_notes"] == "Approved by senior asset manager"


# ==============================================================
# 2. Multi-Day Waiting States & Resumption Tests
# ==============================================================

@patch("agents.graphs.maintenance.nodes.interrupt")
def test_schedule_and_await_technician_visit(mock_interrupt):
    mock_interrupt.return_value = {"confirmed": True}
    state = create_initial_state()
    updates = schedule_and_await_technician(state)
    assert updates["status"] == "technician_visited"
    assert updates["technician_confirmed"] is True


@patch("agents.graphs.maintenance.nodes.interrupt")
def test_order_parts_and_await_delivery(mock_interrupt):
    mock_interrupt.return_value = {"delivered": True}
    state = create_initial_state()
    state["parts_needed"] = [{"part_name": "Hydraulic Pump", "unit_price": 750.0}]
    updates = order_parts_and_await_delivery(state)
    assert updates["status"] == "parts_delivered"
    assert updates["parts_delivered"] is True


def test_execute_maintenance_updates_db():
    state = create_initial_state()
    state["equipment_id"] = 3
    updates = execute_maintenance(state)
    assert updates["status"] == "maintenance_in_progress"

    with get_db_connection() as conn:
        row = conn.execute("SELECT status FROM Equipment WHERE equipment_id = 3").fetchone()
        assert row["status"] == "maintenance"


@patch("agents.graphs.maintenance.nodes.interrupt")
def test_await_operational_testing_passed(mock_interrupt):
    mock_interrupt.return_value = {"outcome": "passed", "notes": "Spray pressure stable at 30 PSI"}
    state = create_initial_state()
    updates = await_operational_testing(state)
    assert updates["testing_result"] == "passed"


def test_evaluate_testing_routing():
    assert evaluate_testing({"testing_result": "passed"})["status"] == "testing_passed"
    assert evaluate_testing({"testing_result": "failed"})["status"] == "testing_failed"
    assert evaluate_testing({"testing_result": "unknown"})["status"] == "testing_invalid"


def test_close_case_restores_idle():
    state = create_initial_state()
    state["equipment_id"] = 3
    updates = close_case(state)
    assert updates["status"] == "closed"

    with get_db_connection() as conn:
        row = conn.execute("SELECT status FROM Equipment WHERE equipment_id = 3").fetchone()
        assert row["status"] == "idle"


# ==============================================================
# 3. Unplanned Failure Ticket & Checkpoint Recovery Tests
# ==============================================================

def test_unplanned_failure_ticket_creation_and_recovery():
    mem = MemorySaver()
    graph = build_maintenance_graph(checkpointer=mem)
    thread_id = "test_ticket_failure_maint_999"

    # 1. Directly invoke handle_failure to simulate ticket generation on error
    fail_state = create_initial_state(thread_id=thread_id)
    fail_state["failed_node"] = "order_parts_and_await_delivery"
    fail_state["error_message"] = "Parts Inventory Gateway 504 Gateway Timeout"
    updates = handle_failure(fail_state)
    assert updates["status"] == "failed"
    ticket_id = updates["ticket_id"]
    assert ticket_id is not None

    # 2. Verify ticket opened in Tickets table
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT ticket_id, status, failed_node, error_message FROM Tickets WHERE ticket_id = ?",
            (ticket_id,),
        ).fetchone()
        assert row is not None
        assert row["status"] == "open"
        assert row["failed_node"] == "order_parts_and_await_delivery"
        assert "504" in row["error_message"]

    # 3. Resolve ticket via platform seam and resume
    summary = resolve_maintenance_ticket_and_resume(
        ticket_id=ticket_id,
        resolution_notes="Inventory cache flushed and connection restored by admin",
        graph=graph,
        state_patch={"simulated_error_node": None, "simulated_error_message": None},
    )
    assert summary["resolved_ticket_id"] == ticket_id
    assert summary["resumed_from_node"] == "schedule_and_await_technician"


# ==============================================================
# 4. Durable SQLite Checkpoint Crash-and-Resume Test
# ==============================================================

def test_durable_sqlite_crash_and_resume(tmp_path):
    """
    Tests durable persistence: state is written to SQLite, process 'crashes' (graph destroyed),
    a new graph process restarts from disk, and resumes without repeating completed steps.
    """
    from langgraph.checkpoint.sqlite import SqliteSaver

    db_file = str(tmp_path / "maint_durable.sqlite")
    conn1 = sqlite3.connect(db_file, check_same_thread=False)
    cp1 = SqliteSaver(conn1)

    graph1 = build_maintenance_graph(checkpointer=cp1)
    thread_id = "thread_maint_crash_777"
    config = {"configurable": {"thread_id": thread_id}}

    # Step 1: Run Turn 1 -> pauses at HITL cost approval (> $500)
    initial_input = create_initial_state(
        issue="Sprayer SPR-3001 hydraulic main pump cracked and leaking fluid",
        thread_id=thread_id,
    )
    graph1.invoke(initial_input, config=config)
    snap1 = graph1.get_state(config)
    assert len(snap1.tasks) > 0
    assert snap1.values.get("hitl_required") is True
    assert snap1.values.get("total_cost") > 500.0

    # SIMULATE CRASH: Destroy process 1
    conn1.close()
    del graph1

    # Step 2: New process boots from same SQLite database
    conn2 = sqlite3.connect(db_file, check_same_thread=False)
    cp2 = SqliteSaver(conn2)
    graph2 = build_maintenance_graph(checkpointer=cp2)

    # Verify state survived crash
    recovered_snap = graph2.get_state(config)
    assert recovered_snap.values.get("hitl_required") is True
    assert recovered_snap.values.get("status") == "cost_estimated"

    # Step 3: Admin approves HITL -> advances to await_technician_visit
    graph2.invoke(Command(resume={"approved": True, "notes": "Approved post-crash"}), config=config)
    snap2 = graph2.get_state(config)
    assert len(snap2.tasks) > 0
    assert snap2.values.get("hitl_status") == "approved"

    # Step 4: Technician arrival confirmed -> advances to await_parts_delivery
    graph2.invoke(Command(resume={"confirmed": True}), config=config)
    snap3 = graph2.get_state(config)
    assert snap3.values.get("technician_confirmed") is True

    # Step 5: Parts delivered -> executes maintenance -> advances to await_operational_testing
    graph2.invoke(Command(resume={"delivered": True}), config=config)
    snap4 = graph2.get_state(config)
    assert snap4.values.get("parts_delivered") is True

    # Step 6: Operational test passed -> finishes case cleanly
    graph2.invoke(Command(resume={"outcome": "passed", "notes": "Pressure holding steady"}), config=config)
    final_snap = graph2.get_state(config)
    assert len(final_snap.tasks) == 0
    assert final_snap.values.get("status") == "closed"
    conn2.close()

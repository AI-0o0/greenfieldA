"""
tests/test_finance_agent.py

Unit & Integration Tests for Greenfield Finance Agent Graph.
Tests all paths in agent/workflows/finance_graph.mmd including Advice, Financing,
HITL admin reviews, Document validation loops, Provider responses, and Farmer confirmations.
"""

import pytest
from langgraph.checkpoint.memory import MemorySaver
from agent.workflows.finance_agent import (
    build_finance_graph,
    create_finance_agent,
    run_finance_turn,
    FinanceState,
    get_db_connection,
)


@pytest.fixture(autouse=True)
def ensure_db_clean():
    with get_db_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO Customers (customer_id, company_name, credit_hold) VALUES (1, 'Nile Delta Farms', 0)")
        conn.execute("INSERT OR IGNORE INTO Customers (customer_id, company_name, credit_hold) VALUES (2, 'Behera Agro Cooperative', 1)")
        conn.execute("INSERT OR IGNORE INTO Customers (customer_id, company_name, credit_hold) VALUES (3, 'Fayoum Green Estates', 0)")
        conn.execute("UPDATE Customers SET credit_hold = 0 WHERE customer_id = 1")
        conn.execute("UPDATE Customers SET credit_hold = 1 WHERE customer_id = 2")
        conn.commit()


# ==============================================================================
# Helpers
# ==============================================================================

def has_log(result: dict, tag: str) -> bool:
    return any(tag in str(item) for item in result.get("execution_log", []))


# ==============================================================================
# Financial Advice Path Tests
# ==============================================================================

def test_advice_equipment_path():
    """Tests financial advice workflow routing through equipment specialist."""
    graph = create_finance_agent(interactive=False)
    state_input: FinanceState = {
        "farmer_id": 1,
        "farmer_request": "Should I lease or purchase a new high-clearance sprayer SPR-3001 for next season?",
        "request_type": "advice",
        "specialist_type": "equipment",
    }
    result = graph.invoke(state_input)

    assert result["request_type"] == "advice"
    assert has_log(result, "EQUIPMENT")
    assert has_log(result, "OPTIONS")
    assert has_log(result, "TOT")
    assert has_log(result, "RAG")
    assert has_log(result, "RECOMMEND")
    assert result.get("recommendation") is not None
    assert len(result.get("financial_options", [])) > 0


def test_advice_crop_path():
    """Tests financial advice workflow routing through crop specialist."""
    graph = create_finance_agent(interactive=False)
    state_input: FinanceState = {
        "farmer_id": 1,
        "farmer_request": "What is the expected yield ROI and seasonal cashflow for wheat on Field 1?",
        "request_type": "advice",
        "specialist_type": "crop",
    }
    result = graph.invoke(state_input)

    assert result["request_type"] == "advice"
    assert has_log(result, "CROP")
    assert has_log(result, "OPTIONS")
    assert has_log(result, "TOT")
    assert has_log(result, "RAG")
    assert has_log(result, "RECOMMEND")
    assert result.get("recommendation") is not None


def test_advice_general_path():
    """Tests financial advice workflow with no domain specialist needed."""
    graph = create_finance_agent(interactive=False)
    state_input: FinanceState = {
        "farmer_id": 1,
        "farmer_request": "General working capital budgeting advice for farm operations next quarter.",
        "request_type": "advice",
        "specialist_type": "no",
    }
    result = graph.invoke(state_input)

    assert result["request_type"] == "advice"
    assert has_log(result, "OPTIONS")
    assert has_log(result, "TOT")
    assert has_log(result, "RECOMMEND")


# ==============================================================================
# Financing Request Path Tests
# ==============================================================================

def test_financing_ineligible_rejection():
    """Tests customer on credit hold being rejected immediately at eligibility step."""
    graph = create_finance_agent(interactive=False)
    state_input: FinanceState = {
        "farmer_id": 2,  # Customer 2 has credit_hold = 1
        "farmer_request": "I want to apply for a $30,000 seasonal crop loan.",
        "request_type": "financing",
    }
    result = graph.invoke(state_input)

    assert result["request_type"] == "financing"
    assert result.get("eligibility_status") is False
    assert has_log(result, "REJECT")
    assert "credit hold" in (result.get("rejection_reason") or "").lower()


def test_financing_successful_standard_path():
    """Tests standard financing path without HITL (amount < $50k, valid docs)."""
    graph = create_finance_agent(interactive=False)
    state_input: FinanceState = {
        "farmer_id": 1,
        "farmer_request": "Need $35,000 loan for irrigation upgrades.",
        "request_type": "financing",
        "documents_submitted": {
            "government_id": "id_doc.pdf",
            "farm_tax_return": "tax_2025.pdf",
            "bank_statements": "bank_stmts.pdf",
            "land_deed_or_lease": "deed.pdf",
        },
        "financial_analysis": {
            "assessed_amount": 35000.0,
            "dscr": 1.6,
            "risk_level": "low",
            "recommended_term_months": 36,
            "max_borrowing_capacity": 60000.0,
        },
        "provider_response": "approved",
        "farmer_accepts": True,
    }
    result = graph.invoke(state_input)

    assert result.get("eligibility_status") is True
    assert result.get("documents_valid") is True
    assert result.get("hitl_required") is False
    assert has_log(result, "SUBMIT")
    assert has_log(result, "FARMER_CONFIRM")
    assert has_log(result, "PROCESS")
    assert has_log(result, "VERIFY")
    assert result.get("transaction_verification", {}).get("verified") is True


def test_financing_hitl_admin_approval():
    """Tests large loan (>= $50k) triggering HITL admin review and manager approval."""
    graph = create_finance_agent(interactive=False)
    state_input: FinanceState = {
        "farmer_id": 1,
        "farmer_request": "Need $80,000 financing for new tractor equipment.",
        "request_type": "financing",
        "documents_submitted": {
            "government_id": "id_doc.pdf",
            "farm_tax_return": "tax_2025.pdf",
            "bank_statements": "bank_stmts.pdf",
            "land_deed_or_lease": "deed.pdf",
        },
        "financial_analysis": {
            "assessed_amount": 80000.0,
            "dscr": 1.35,
            "risk_level": "medium",
            "recommended_term_months": 48,
            "max_borrowing_capacity": 100000.0,
        },
        "admin_decision": "approve",
        "provider_response": "approved",
        "farmer_accepts": True,
    }
    result = graph.invoke(state_input)

    assert result.get("hitl_required") is True
    assert has_log(result, "ADMIN")
    assert has_log(result, "SUBMIT")
    assert has_log(result, "PROCESS")
    assert has_log(result, "VERIFY")


def test_financing_hitl_admin_rejection():
    """Tests HITL admin review where manager rejects application."""
    graph = create_finance_agent(interactive=False)
    state_input: FinanceState = {
        "farmer_id": 1,
        "farmer_request": "Need $95,000 loan.",
        "request_type": "financing",
        "documents_submitted": {
            "government_id": "id_doc.pdf",
            "farm_tax_return": "tax_2025.pdf",
            "bank_statements": "bank_stmts.pdf",
            "land_deed_or_lease": "deed.pdf",
        },
        "financial_analysis": {
            "assessed_amount": 95000.0,
            "dscr": 1.1,
            "risk_level": "high",
            "recommended_term_months": 60,
            "max_borrowing_capacity": 50000.0,
        },
        "admin_decision": "reject",
    }
    result = graph.invoke(state_input)

    assert result.get("hitl_required") is True
    assert has_log(result, "ADMIN")
    assert has_log(result, "REJECT")
    assert not has_log(result, "PROCESS")


def test_financing_provider_rejection_to_alternatives():
    """Tests provider declining application, routing to alternative option generation and recommendation."""
    graph = create_finance_agent(interactive=False)
    state_input: FinanceState = {
        "farmer_id": 1,
        "farmer_request": "Need $40,000 loan.",
        "request_type": "financing",
        "documents_submitted": {
            "government_id": "id_doc.pdf",
            "farm_tax_return": "tax_2025.pdf",
            "bank_statements": "bank_stmts.pdf",
            "land_deed_or_lease": "deed.pdf",
        },
        "financial_analysis": {
            "assessed_amount": 40000.0,
            "dscr": 1.5,
            "risk_level": "low",
            "recommended_term_months": 36,
            "max_borrowing_capacity": 50000.0,
        },
        "provider_response": "rejected",
    }
    result = graph.invoke(state_input)

    assert has_log(result, "PROVIDER_REJECTED")
    assert has_log(result, "ALTERNATIVE")
    assert has_log(result, "RECOMMEND")
    assert len(result.get("alternative_options", [])) > 0


def test_financing_farmer_declined_to_alternatives():
    """Tests farmer rejecting offered provider terms, routing to alternative option generation."""
    graph = create_finance_agent(interactive=False)
    state_input: FinanceState = {
        "farmer_id": 1,
        "farmer_request": "Need $30,000 loan.",
        "request_type": "financing",
        "documents_submitted": {
            "government_id": "id_doc.pdf",
            "farm_tax_return": "tax_2025.pdf",
            "bank_statements": "bank_stmts.pdf",
            "land_deed_or_lease": "deed.pdf",
        },
        "financial_analysis": {
            "assessed_amount": 30000.0,
            "dscr": 1.6,
            "risk_level": "low",
            "recommended_term_months": 24,
            "max_borrowing_capacity": 50000.0,
        },
        "provider_response": "approved",
        "farmer_accepts": False,  # Farmer declines terms
    }
    result = graph.invoke(state_input)

    assert has_log(result, "FARMER_CONFIRM")
    assert has_log(result, "ALTERNATIVE")
    assert has_log(result, "RECOMMEND")
    assert not has_log(result, "PROCESS")


# ==============================================================================
# Interactive Turn / Interrupt Resumption Tests
# ==============================================================================

def test_interactive_turn_document_upload_resumption():
    """Tests interactive checkpointing across multiple turns: documents, provider, and farmer acceptance."""
    mem = MemorySaver()
    graph = create_finance_agent(checkpointer=mem, interactive=True)
    thread_id = "test_thread_interactive_docs_101"
    config = {"configurable": {"thread_id": thread_id}}

    # Turn 1: Initial financing request -> pauses before wait_farmer
    initial_state = {
        "farmer_id": 1,
        "farmer_request": "I want to apply for $20,000 equipment financing.",
        "request_type": "financing",
    }
    run_finance_turn(graph, thread_id, initial_state)
    state_snap1 = graph.get_state(config)
    assert "wait_farmer" in state_snap1.next

    # Turn 2: Farmer uploads documents -> resumes through validation & submit -> pauses before wait_provider
    doc_update = {
        "documents_submitted": {
            "government_id": "id.pdf",
            "farm_tax_return": "tax.pdf",
            "bank_statements": "bank.pdf",
            "land_deed_or_lease": "deed.pdf",
        },
        "financial_analysis": {
            "assessed_amount": 20000.0,
            "dscr": 1.8,
            "risk_level": "low",
            "recommended_term_months": 24,
            "max_borrowing_capacity": 50000.0,
        },
    }
    run_finance_turn(graph, thread_id, doc_update)
    state_snap2 = graph.get_state(config)
    assert "wait_provider" in state_snap2.next

    # Turn 3: Provider returns approval -> pauses before farmer_confirm
    provider_update = {
        "provider_response": "approved",
    }
    run_finance_turn(graph, thread_id, provider_update)
    state_snap3 = graph.get_state(config)
    assert "farmer_confirm" in state_snap3.next

    # Turn 4: Farmer accepts loan terms -> completes process and verification
    farmer_update = {
        "farmer_accepts": True,
    }
    final_snap = run_finance_turn(graph, thread_id, farmer_update)
    assert has_log(final_snap, "VERIFY")
    assert final_snap.get("transaction_verification", {}).get("verified") is True


# ==============================================================================
# Rubric Test 1: Durable SQLite Checkpointing & Crash-and-Resume
# ==============================================================================

def test_sqlite_checkpointer_crash_and_resume(tmp_path):
    """
    Tests durable persistence: state is written to SQLite, process 'crashes' (graph object destroyed),
    a new graph process starts up from the same SQLite DB, and resumes from the exact checkpoint.
    """
    import os
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver

    db_file = str(tmp_path / "durable_checkpoints.sqlite")
    conn1 = sqlite3.connect(db_file, check_same_thread=False)
    cp1 = SqliteSaver(conn1)

    # Process 1: Start graph and run Turn 1 -> pauses at wait_farmer
    graph1 = create_finance_agent(checkpointer=cp1, interactive=True)
    thread_id = "thread_crash_test_999"
    config = {"configurable": {"thread_id": thread_id}}

    initial_input = {
        "farmer_id": 1,
        "farmer_request": "Need $75,000 capital loan for new tractor fleet.",
        "request_type": "financing",
    }
    run_finance_turn(graph1, thread_id, initial_input)
    snap1 = graph1.get_state(config)
    assert "wait_farmer" in snap1.next

    # Turn 2: Farmer uploads docs with high loan amount ($75k) -> advances past validation & analysis -> pauses at admin_review
    turn2_input = {
        "documents_submitted": {
            "government_id": "id.pdf",
            "farm_tax_return": "tax.pdf",
            "bank_statements": "bank.pdf",
            "land_deed_or_lease": "deed.pdf",
        },
        "financial_analysis": {
            "assessed_amount": 75000.0,
            "dscr": 1.4,
            "risk_level": "medium",
            "recommended_term_months": 48,
            "max_borrowing_capacity": 100000.0,
        },
    }
    run_finance_turn(graph1, thread_id, turn2_input)
    snap2 = graph1.get_state(config)
    assert "admin_review" in snap2.next
    assert snap2.values.get("hitl_required") is True

    # SIMULATE CRASH: Close connection and destroy graph1
    conn1.close()
    del graph1

    # Process 2: New process opens SQLite checkpointer from disk
    conn2 = sqlite3.connect(db_file, check_same_thread=False)
    cp2 = SqliteSaver(conn2)
    graph2 = create_finance_agent(checkpointer=cp2, interactive=True)

    # Verify state survived the restart
    recovered_snap = graph2.get_state(config)
    assert "admin_review" in recovered_snap.next
    assert recovered_snap.values.get("hitl_required") is True
    assert has_log(recovered_snap.values, "TOT_FIN")

    # Turn 3: Admin reviews and approves -> advances to wait_provider
    turn3_input = {
        "admin_decision": "approve",
        "admin_feedback": "Approved by credit committee after process restart",
    }
    run_finance_turn(graph2, thread_id, turn3_input)
    snap3 = graph2.get_state(config)
    assert "wait_provider" in snap3.next

    # Turn 4: Provider approves -> pauses at farmer_confirm
    run_finance_turn(graph2, thread_id, {"provider_response": "approved"})
    snap4 = graph2.get_state(config)
    assert "farmer_confirm" in snap4.next

    # Turn 5: Farmer confirms terms -> processes and verifies
    final_snap = run_finance_turn(graph2, thread_id, {"farmer_accepts": True})
    assert has_log(final_snap, "ADMIN")
    assert has_log(final_snap, "VERIFY")
    assert final_snap.get("transaction_verification", {}).get("verified") is True
    conn2.close()


# ==============================================================================
# Rubric Test 2: HITL Task Queue & Platform Resumption Helper
# ==============================================================================

def test_hitl_task_queue_and_resumption():
    """
    Tests explicit HITL policy triggers opening a task in HITL_Tasks table,
    and platform admin resolving it via resume_hitl_task.
    """
    from agent.workflows.finance_agent import fetch_pending_hitl_tasks, resume_hitl_task

    mem = MemorySaver()
    graph = create_finance_agent(checkpointer=mem, interactive=True)
    thread_id = "thread_hitl_queue_test_777"
    config = {"configurable": {"thread_id": thread_id}}

    # Turn 1: Initial request
    run_finance_turn(graph, thread_id, {
        "farmer_id": 1,
        "farmer_request": "Apply for $85,000 harvester expansion loan.",
        "request_type": "financing",
    })

    # Turn 2: Farmer uploads documents -> triggers HITL pause at admin_review
    run_finance_turn(graph, thread_id, {
        "documents_submitted": {
            "government_id": "id.pdf",
            "farm_tax_return": "tax.pdf",
            "bank_statements": "bank.pdf",
            "land_deed_or_lease": "deed.pdf",
        },
        "financial_analysis": {
            "assessed_amount": 85000.0,
            "dscr": 1.15,
            "risk_level": "high",
            "recommended_term_months": 60,
            "max_borrowing_capacity": 90000.0,
        },
    })
    state_snap = graph.get_state(config)
    assert "admin_review" in state_snap.next

    # Check pending task in HITL_Tasks table
    pending = fetch_pending_hitl_tasks()
    matching = [t for t in pending if t["thread_id"] == thread_id]
    assert len(matching) > 0
    task = matching[0]
    assert task["assessed_amount"] == 85000.0
    assert task["status"] == "pending"

    # Admin acts via platform helper -> advances to wait_provider
    snap_after_hitl = resume_hitl_task(
        task_id=task["task_id"],
        decision="approve",
        admin_feedback="Manager approved with secondary equipment collateral",
        graph=graph,
    )
    assert "wait_provider" in graph.get_state(config).next

    # Provider & Farmer confirmation turns
    run_finance_turn(graph, thread_id, {"provider_response": "approved"})
    final_snap = run_finance_turn(graph, thread_id, {"farmer_accepts": True})
    assert has_log(final_snap, "ADMIN")
    assert has_log(final_snap, "VERIFY")
    assert final_snap.get("transaction_verification", {}).get("verified") is True


# ==============================================================================
# Rubric Test 3: Ticket System for Unplanned Mid-Node Failures & Recovery
# ==============================================================================

def test_ticket_system_failure_capture_and_recovery():
    """
    Tests that an unplanned mid-node exception is safely caught, persisted into Tickets table,
    and can be resolved & resumed from the exact checkpoint without restarting from the top.
    """
    from agent.workflows.finance_agent import fetch_tickets, resolve_ticket_and_resume

    mem = MemorySaver()
    graph = create_finance_agent(checkpointer=mem, interactive=True)
    thread_id = "thread_ticket_failure_test_555"
    config = {"configurable": {"thread_id": thread_id}}

    # Turn 1: Initial request -> pauses at wait_farmer
    run_finance_turn(graph, thread_id, {
        "farmer_id": 1,
        "farmer_request": "Apply for $30,000 loan.",
        "request_type": "financing",
    })

    # Turn 2: Farmer uploads docs with simulated failure in financial_analysis node
    fail_input = {
        "documents_submitted": {
            "government_id": "id.pdf",
            "farm_tax_return": "tax.pdf",
            "bank_statements": "bank.pdf",
            "land_deed_or_lease": "deed.pdf",
        },
        "simulated_error_node": "financial_analysis",
        "simulated_error_message": "Valuation Service HTTP 503 Service Unavailable",
    }

    result = run_finance_turn(graph, thread_id, fail_input)
    assert result.get("error") is not None
    assert result.get("failed_node") == "financial_analysis"

    # Check that a ticket was opened in Tickets table
    tickets = fetch_tickets(status="open")
    matching = [t for t in tickets if t["thread_id"] == thread_id]
    assert len(matching) > 0
    ticket = matching[0]
    assert "Valuation Service HTTP 503" in ticket["error_message"]
    assert ticket["status"] == "open"

    # Admin resolves the ticket by patching valid financial analysis and resuming
    patch = {
        "simulated_error_node": None,
        "simulated_error_message": None,
        "financial_analysis": {
            "assessed_amount": 30000.0,
            "dscr": 1.6,
            "risk_level": "low",
            "recommended_term_months": 36,
            "max_borrowing_capacity": 50000.0,
        },
    }
    # Resumes through submit -> pauses at wait_provider
    snap_after_ticket = resolve_ticket_and_resume(
        ticket_id=ticket["ticket_id"],
        state_patch=patch,
        resolution_notes="Valuation restored manually by admin",
        graph=graph,
    )
    assert snap_after_ticket.get("error") is None
    assert "wait_provider" in graph.get_state(config).next

    # Complete provider and farmer confirmation turns
    run_finance_turn(graph, thread_id, {"provider_response": "approved"})
    final_snap = run_finance_turn(graph, thread_id, {"farmer_accepts": True})
    assert has_log(final_snap, "VERIFY")
    assert final_snap.get("transaction_verification", {}).get("verified") is True


# ==============================================================================
# Rubric Test 4: Document Validation Cycles & Rejection Loops
# ==============================================================================

def test_document_validation_cycle():
    """Tests cycling between validate_documents and collect_documents when documents are missing."""
    mem = MemorySaver()
    graph = create_finance_agent(checkpointer=mem, interactive=True)
    thread_id = "thread_doc_cycle_111"
    config = {"configurable": {"thread_id": thread_id}}

    # Turn 1: Initial request -> pauses at wait_farmer
    run_finance_turn(graph, thread_id, {
        "farmer_id": 1,
        "farmer_request": "Need $25,000 loan.",
        "request_type": "financing",
    })
    snap1 = graph.get_state(config)
    assert "wait_farmer" in snap1.next

    # Turn 2: Farmer uploads incomplete documents (missing tax return)
    run_finance_turn(graph, thread_id, {
        "documents_submitted": {"government_id": "id.pdf"},
    })
    snap2 = graph.get_state(config)
    # Since documents were invalid, the cycle routed back to collect_documents -> wait_farmer
    assert "wait_farmer" in snap2.next
    assert snap2.values.get("documents_valid") is False

    # Turn 3: Farmer uploads complete set of documents -> advances to wait_provider
    run_finance_turn(graph, thread_id, {
        "documents_submitted": {
            "government_id": "id.pdf",
            "farm_tax_return": "tax.pdf",
            "bank_statements": "bank.pdf",
            "land_deed_or_lease": "deed.pdf",
        },
        "financial_analysis": {
            "assessed_amount": 25000.0,
            "dscr": 1.7,
            "risk_level": "low",
            "recommended_term_months": 24,
            "max_borrowing_capacity": 50000.0,
        },
    })
    snap3 = graph.get_state(config)
    assert snap3.values.get("documents_valid") is True
    assert "wait_provider" in snap3.next

    # Turn 4 & 5: Complete provider approval and farmer acceptance
    run_finance_turn(graph, thread_id, {"provider_response": "approved"})
    final_snap = run_finance_turn(graph, thread_id, {"farmer_accepts": True})
    assert has_log(final_snap, "VERIFY")
    assert final_snap.get("transaction_verification", {}).get("verified") is True





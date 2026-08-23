"""
tests/test_crop_disease.py

Comprehensive Unit & Integration Test Suite for Greenfield Crop Disease State Graph Agent.
Tests all nodes, edges, conditional routers, HITL pauses, farmer confirmations,
treatment execution, observation loops, re-diagnosis cycles, failure ticketing,
and durable graph checkpointer execution.
"""

import asyncio
import pytest
import sqlite3
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from mcp_server.tools import get_db_connection
from agents.graphs.crop_disease import (
    CaseState,
    DiagnosisResult,
    collect_crop_data,
    make_diagnose_node,
    propose_treatment,
    hitl_check,
    await_farmer_confirmation,
    execute_treatment,
    await_observation,
    evaluate_result,
    re_diagnose,
    handle_failure,
    close_case,
    MAX_RETRIES,
    build_crop_disease_graph,
    route_after_diagnose,
    route_after_propose_treatment,
    route_after_hitl_check,
    route_after_farmer_confirmation,
    route_after_execute_treatment,
    route_after_evaluate_result,
)


@pytest.fixture(autouse=True)
def setup_test_db():
    """Ensures test database contains required records for crop disease tests."""
    with get_db_connection() as conn:
        # Seed Customer
        conn.execute(
            "INSERT OR IGNORE INTO Customers (customer_id, company_name, credit_hold) "
            "VALUES (1, 'Nile Delta Farms', 0)"
        )
        # Seed Field
        conn.execute(
            "INSERT OR IGNORE INTO Fields (field_id, customer_id, field_name, location, area) "
            "VALUES (1, 1, 'North Plot A', 'Kafr El Sheikh, Block 4', 12.5)"
        )
        # Seed Technician
        conn.execute(
            "INSERT OR IGNORE INTO Technicians (technician_id, full_name, role, authenticated) "
            "VALUES (1, 'Mona Adel', 'dispatcher', 1)"
        )
        # Seed idle sprayer equipment
        conn.execute(
            "INSERT OR IGNORE INTO Equipment (equipment_id, serial_number, equipment_type, status, current_location) "
            "VALUES (3, 'SPR-3001', 'sprayer', 'idle', 'Depot A')"
        )
        conn.execute("UPDATE Equipment SET status = 'idle' WHERE equipment_id = 3")

        # Seed Chemicals
        conn.execute(
            "INSERT OR IGNORE INTO Chemicals (chemical_id, name, hazard_class, requires_signoff) "
            "VALUES (1, 'Glyphosate', 'restricted', 1)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO Chemicals (chemical_id, name, hazard_class, requires_signoff) "
            "VALUES (3, 'Neem Oil Extract', 'low', 0)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO Chemicals (chemical_id, name, hazard_class, requires_signoff) "
            "VALUES (4, 'Foliar Fertilizer', 'low', 0)"
        )

        # Seed initial Crop_Cases row for testing
        conn.execute(
            "INSERT OR REPLACE INTO Crop_Cases (case_id, thread_id, customer_id, field_id, status, retry_count) "
            "VALUES (100, 'test_thread_crop_100', 1, 1, 'case_created', 0)"
        )
        conn.commit()


def create_initial_state(
    case_id: int = 100,
    thread_id: str = "test_thread_crop_100",
    report: str = "Leaves have yellow spots and powdery mildew on wheat in field 1.",
) -> CaseState:
    """Helper to construct a valid initial CaseState."""
    return {
        "case_id": case_id,
        "thread_id": thread_id,
        "status": "case_created",
        "messages": [HumanMessage(content=report)],
        "customer_id": 1,
        "field_id": 1,
        "rag_context": "",
        "memory_context": "",
        "crop_data": {},
        "diagnosis": {},
        "proposed_treatment": {},
        "dispatch_id": None,
        "farmer_confirmed": None,
        "observation_result": None,
        "retry_count": 0,
        "hitl_required": False,
        "hitl_status": None,
        "hitl_task_id": None,
        "ticket_id": None,
        "ticket_status": None,
    }


# ==============================================================================
# 1. Schema and Model Verification Tests
# ==============================================================================

def test_diagnosis_result_pydantic_schema():
    """Tests DiagnosisResult model serialization and validation."""
    valid_data = {
        "disease_name": "Powdery Mildew",
        "confidence": 0.95,
        "reasoning": "Observed white powdery patches on upper leaf surface.",
        "recommended_chemical_names": ["Neem Oil Extract"],
    }
    result = DiagnosisResult(**valid_data)
    assert result.disease_name == "Powdery Mildew"
    assert result.confidence == 0.95
    assert result.recommended_chemical_names == ["Neem Oil Extract"]

    # Extra fields should be forbidden per model_config
    with pytest.raises(Exception):
        DiagnosisResult(**{**valid_data, "unsupported_field": "invalid"})


# ==============================================================================
# 2. Conditional Edge Routing Tests
# ==============================================================================

def test_route_after_diagnose():
    """Tests conditional routing after diagnose node."""
    # 1. Grounded diagnosis -> propose_treatment
    state_grounded: CaseState = {"diagnosis": {"grounded": True}, "retry_count": 0}  # type: ignore
    assert route_after_diagnose(state_grounded) == "propose_treatment"

    # 2. Ungrounded with retries left -> diagnose (retry loop)
    state_retry: CaseState = {"diagnosis": {"grounded": False}, "retry_count": 1}  # type: ignore
    assert route_after_diagnose(state_retry) == "diagnose"

    # 3. Ungrounded with retries exhausted -> handle_failure
    state_failed: CaseState = {"diagnosis": {"grounded": False}, "retry_count": MAX_RETRIES}  # type: ignore
    assert route_after_diagnose(state_failed) == "handle_failure"


def test_route_after_propose_treatment():
    """Tests conditional routing after propose_treatment node."""
    # Success -> hitl_check
    state_ok: CaseState = {"proposed_treatment": {"chemical_id": 3}}  # type: ignore
    assert route_after_propose_treatment(state_ok) == "hitl_check"

    # Error -> handle_failure
    state_err: CaseState = {"proposed_treatment": {"error": "no_whitelisted_chemical_match"}}  # type: ignore
    assert route_after_propose_treatment(state_err) == "handle_failure"


def test_route_after_hitl_check():
    """Tests conditional routing after hitl_check node."""
    # Approved or not required -> await_farmer_confirmation
    state_app: CaseState = {"hitl_status": "approved"}  # type: ignore
    assert route_after_hitl_check(state_app) == "await_farmer_confirmation"

    state_none: CaseState = {"hitl_status": None}  # type: ignore
    assert route_after_hitl_check(state_none) == "await_farmer_confirmation"

    # Rejected by admin -> propose_treatment for revision
    state_rej: CaseState = {"hitl_status": "rejected"}  # type: ignore
    assert route_after_hitl_check(state_rej) == "propose_treatment"


def test_route_after_farmer_confirmation():
    """Tests conditional routing after await_farmer_confirmation node."""
    state_conf: CaseState = {"status": "farmer_confirmed"}  # type: ignore
    assert route_after_farmer_confirmation(state_conf) == "execute_treatment"

    state_decl: CaseState = {"status": "declined"}  # type: ignore
    assert route_after_farmer_confirmation(state_decl) == "close_case"


def test_route_after_execute_treatment():
    """Tests conditional routing after execute_treatment node."""
    state_ok: CaseState = {"proposed_treatment": {"chemical_id": 3}}  # type: ignore
    assert route_after_execute_treatment(state_ok) == "await_observation"

    state_err: CaseState = {"proposed_treatment": {"error": "dispatch_failed"}}  # type: ignore
    assert route_after_execute_treatment(state_err) == "handle_failure"


def test_route_after_evaluate_result():
    """Tests conditional routing after evaluate_result node."""
    assert route_after_evaluate_result({"status": "recovered"}) == "close_case"  # type: ignore
    assert route_after_evaluate_result({"status": "improved"}) == "await_observation"  # type: ignore
    assert route_after_evaluate_result({"status": "worsened"}) == "re_diagnose"  # type: ignore
    assert route_after_evaluate_result({"status": "invalid_observation"}) == "handle_failure"  # type: ignore


# ==============================================================================
# 3. Individual Node Handler Tests
# ==============================================================================

def test_collect_crop_data_node():
    """Tests collect_crop_data entry node parses HumanMessage and persists state."""
    state = create_initial_state(report="Severe rust on wheat crop leaves.")
    updates = collect_crop_data(state)

    assert updates["status"] == "collect_crop_data"
    assert updates["retry_count"] == 0
    assert updates["crop_data"]["raw_report"] == "Severe rust on wheat crop leaves."
    assert updates["crop_data"]["customer_id"] == 1
    assert updates["crop_data"]["field_id"] == 1

    # Verify persisted in Crop_Cases DB
    with get_db_connection() as conn:
        row = conn.execute("SELECT status, crop_data FROM Crop_Cases WHERE case_id = 100").fetchone()
        assert row["status"] == "collect_crop_data"
        assert "Severe rust" in row["crop_data"]


@patch("agents.graphs.crop_disease.nodes.hybrid_search")
def test_make_diagnose_node_no_rag_chunks(mock_search):
    """Tests diagnose node when hybrid search returns no matching chunks."""
    mock_search.return_value = []
    diagnose_fn = make_diagnose_node(llm=MagicMock())

    state = create_initial_state()
    state["crop_data"] = {"raw_report": "Unknown strange plant defect"}
    state["retry_count"] = 0

    updates = diagnose_fn(state)
    assert updates["status"] == "diagnose"
    assert updates["diagnosis"]["grounded"] is False
    assert updates["diagnosis"]["reason"] == "no_knowledge_base_results"
    assert updates["retry_count"] == 1


@patch("agents.graphs.crop_disease.nodes.hybrid_search")
@patch("agents.graphs.crop_disease.nodes.self_rag_verify")
def test_make_diagnose_node_self_rag_irrelevant(mock_verify, mock_search):
    """Tests diagnose node when self-rag flags retrieved context as irrelevant."""
    mock_search.return_value = ["Some unrelated soil pH document."]
    mock_verify.return_value = MagicMock(is_relevant=False)
    diagnose_fn = make_diagnose_node(llm=MagicMock())

    state = create_initial_state()
    state["crop_data"] = {"raw_report": "Yellow aphids on corn"}
    state["retry_count"] = 0

    updates = diagnose_fn(state)
    assert updates["status"] == "diagnose"
    assert updates["diagnosis"]["grounded"] is False
    assert updates["diagnosis"]["reason"] == "self_rag_flagged_irrelevant"
    assert updates["retry_count"] == 1


@patch("agents.graphs.crop_disease.nodes.hybrid_search")
@patch("agents.graphs.crop_disease.nodes.self_rag_verify")
def test_make_diagnose_node_success(mock_verify, mock_search):
    """Tests diagnose node when RAG retrieval is relevant and LLM produces structured diagnosis."""
    mock_search.return_value = ["Powdery mildew guide: Treat with Neem Oil Extract."]
    mock_verify.return_value = MagicMock(is_relevant=True)

    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.invoke.return_value = DiagnosisResult(
        disease_name="Powdery Mildew",
        confidence=0.92,
        reasoning="Symptom pattern matches powdery mildew.",
        recommended_chemical_names=["Neem Oil Extract"],
    )
    mock_llm.with_structured_output.return_value = mock_structured

    diagnose_fn = make_diagnose_node(llm=mock_llm)

    state = create_initial_state()
    state["crop_data"] = {"raw_report": "White powder on wheat leaves."}
    state["retry_count"] = 1

    updates = diagnose_fn(state)
    assert updates["status"] == "diagnose"
    assert updates["diagnosis"]["grounded"] is True
    assert updates["diagnosis"]["disease_name"] == "Powdery Mildew"
    assert updates["diagnosis"]["confidence"] == 0.92
    assert updates["diagnosis"]["recommended_chemical_names"] == ["Neem Oil Extract"]
    assert updates["retry_count"] == 0


def test_propose_treatment_low_hazard():
    """Tests propose_treatment resolves whitelisted low-hazard chemical without HITL required."""
    state = create_initial_state()
    state["diagnosis"] = {
        "grounded": True,
        "recommended_chemical_names": ["Neem Oil Extract"],
    }

    updates = propose_treatment(state)
    assert updates["status"] == "propose_treatment"
    assert updates["hitl_required"] is False
    treatment = updates["proposed_treatment"]
    assert treatment["chemical_name"] == "Neem Oil Extract"
    assert treatment["chemical_id"] == 3
    assert treatment["equipment_id"] == 3
    assert treatment["job_type"] == "spray"


def test_propose_treatment_restricted_chemical_requires_hitl():
    """Tests propose_treatment resolves restricted chemical and marks hitl_required=True."""
    state = create_initial_state()
    state["diagnosis"] = {
        "grounded": True,
        "recommended_chemical_names": ["Glyphosate"],
    }

    updates = propose_treatment(state)
    assert updates["status"] == "propose_treatment"
    assert updates["hitl_required"] is True
    assert updates["proposed_treatment"]["chemical_name"] == "Glyphosate"
    assert updates["proposed_treatment"]["chemical_id"] == 1


def test_propose_treatment_unwhitelisted_chemical():
    """Tests propose_treatment records error when recommended chemical is not in DB."""
    state = create_initial_state()
    state["diagnosis"] = {
        "grounded": True,
        "recommended_chemical_names": ["FictionalChemicalX"],
    }

    updates = propose_treatment(state)
    assert updates["status"] == "propose_treatment"
    assert updates["proposed_treatment"]["error"] == "no_whitelisted_chemical_match"


def test_propose_treatment_no_idle_sprayer():
    """Tests propose_treatment records error when no idle sprayer is available."""
    # Set all sprayers to dispatched
    with get_db_connection() as conn:
        conn.execute("UPDATE Equipment SET status = 'dispatched' WHERE equipment_type = 'sprayer'")
        conn.commit()

    try:
        state = create_initial_state()
        state["diagnosis"] = {
            "grounded": True,
            "recommended_chemical_names": ["Neem Oil Extract"],
        }
        updates = propose_treatment(state)
        assert updates["proposed_treatment"]["error"] == "no_idle_sprayer_available"
    finally:
        with get_db_connection() as conn:
            conn.execute("UPDATE Equipment SET status = 'idle' WHERE equipment_id = 3")
            conn.commit()


def test_hitl_check_not_required():
    """Tests hitl_check passes through immediately when signoff is not required."""
    state = create_initial_state()
    state["proposed_treatment"] = {
        "chemical_id": 3,
        "chemical_name": "Neem Oil Extract",
    }

    updates = hitl_check(state)
    assert updates["status"] == "hitl_check"
    assert updates["hitl_required"] is False
    assert updates["hitl_status"] is None


@patch("agents.graphs.crop_disease.nodes.interrupt")
def test_hitl_check_signoff_flow(mock_interrupt):
    """Tests hitl_check opens a Crop_HITL_Tasks record and resumes with approval."""
    mock_interrupt.return_value = {"approved": True, "notes": "Approved by senior agronomist"}

    state = create_initial_state()
    state["diagnosis"] = {"disease_name": "Weed Infestation"}
    state["proposed_treatment"] = {
        "chemical_id": 1,
        "chemical_name": "Glyphosate",
        "hazard_class": "restricted",
    }

    updates = hitl_check(state)
    assert updates["status"] == "hitl_check"
    assert updates["hitl_status"] == "approved"

    # Verify task recorded and updated in Crop_HITL_Tasks
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT status, admin_notes FROM Crop_HITL_Tasks WHERE case_id = 100 ORDER BY task_id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert row["status"] == "approved"
        assert row["admin_notes"] == "Approved by senior agronomist"


@patch("agents.graphs.crop_disease.nodes.interrupt")
def test_await_farmer_confirmation_confirmed(mock_interrupt):
    """Tests await_farmer_confirmation resumes with farmer confirmation True."""
    mock_interrupt.return_value = {"confirmed": True}

    state = create_initial_state()
    state["proposed_treatment"] = {"chemical_name": "Neem Oil Extract"}

    updates = await_farmer_confirmation(state)
    assert updates["status"] == "farmer_confirmed"
    assert updates["farmer_confirmed"] is True


@patch("agents.graphs.crop_disease.nodes.interrupt")
def test_await_farmer_confirmation_declined(mock_interrupt):
    """Tests await_farmer_confirmation resumes with farmer declining treatment."""
    mock_interrupt.return_value = {"confirmed": False}

    state = create_initial_state()
    state["proposed_treatment"] = {"chemical_name": "Neem Oil Extract"}

    updates = await_farmer_confirmation(state)
    assert updates["status"] == "closed"
    assert updates["farmer_confirmed"] is False


def test_execute_treatment_success():
    """Tests execute_treatment dispatches equipment and populates dispatch_id."""
    state = create_initial_state()
    state["hitl_required"] = False
    state["proposed_treatment"] = {
        "equipment_id": 3,
        "field_id": 1,
        "job_type": "spray",
        "chemical_id": 3,
        "customer_id": 1,
    }

    updates = asyncio.run(execute_treatment(state))
    assert updates["status"] == "treatment_started"
    assert updates["dispatch_id"] is not None


def test_execute_treatment_blocked_without_approval():
    """Tests execute_treatment blocks execution if required HITL signoff is missing."""
    state = create_initial_state()
    state["hitl_required"] = True
    state["hitl_status"] = None  # Not yet approved
    state["proposed_treatment"] = {
        "equipment_id": 3,
        "field_id": 1,
        "job_type": "spray",
        "chemical_id": 1,
        "customer_id": 1,
    }

    updates = asyncio.run(execute_treatment(state))
    assert updates["status"] == "execute_treatment"
    assert updates["proposed_treatment"]["error"] == "attempted_execution_without_hitl_approval"


@patch("agents.graphs.crop_disease.nodes.interrupt")
def test_await_observation_node(mock_interrupt):
    """Tests await_observation captures follow-up report from farmer/technician."""
    mock_interrupt.return_value = {"outcome": "recovered", "notes": "No mildew remains."}

    state = create_initial_state()
    state["dispatch_id"] = 10

    updates = await_observation(state)
    assert updates["status"] == "evaluate_result"
    assert updates["observation_result"]["outcome"] == "recovered"
    assert updates["observation_result"]["notes"] == "No mildew remains."


def test_evaluate_result_outcomes():
    """Tests evaluate_result handles all recognized and invalid outcomes."""
    # 1. Recovered
    st_rec = create_initial_state()
    st_rec["observation_result"] = {"outcome": "recovered"}
    assert evaluate_result(st_rec)["status"] == "recovered"

    # 2. Improved
    st_imp = create_initial_state()
    st_imp["observation_result"] = {"outcome": "improved"}
    assert evaluate_result(st_imp)["status"] == "improved"

    # 3. Worsened
    st_wor = create_initial_state()
    st_wor["observation_result"] = {"outcome": "worsened"}
    assert evaluate_result(st_wor)["status"] == "worsened"

    # 4. Invalid outcome
    st_inv = create_initial_state()
    st_inv["observation_result"] = {"outcome": "unrecognized_state"}
    res_inv = evaluate_result(st_inv)
    assert res_inv["status"] == "invalid_observation"
    assert res_inv["observation_result"]["error"] == "unrecognized_outcome"


def test_re_diagnose_node():
    """Tests re_diagnose builds treatment history and resets retry counter."""
    state = create_initial_state()
    state["crop_data"] = {"raw_report": "Leaves yellowing", "treatment_history": []}
    state["proposed_treatment"] = {"chemical_name": "Neem Oil Extract"}
    state["observation_result"] = {"outcome": "worsened", "notes": "Fungus spread to stems."}
    state["retry_count"] = 2

    updates = re_diagnose(state)
    assert updates["status"] == "re_diagnose"
    assert updates["retry_count"] == 0
    history = updates["crop_data"]["treatment_history"]
    assert len(history) == 1
    assert history[0]["outcome"] == "worsened"
    assert history[0]["notes"] == "Fungus spread to stems."


def test_handle_failure_ticket_creation():
    """Tests handle_failure node persists state snapshot to Tickets table with status 'open'."""
    state = create_initial_state()
    state["status"] = "diagnose"
    state["retry_count"] = MAX_RETRIES

    updates = handle_failure(state)
    assert updates["status"] == "failed"
    assert updates["ticket_status"] == "open"
    assert updates["ticket_id"] is not None

    with get_db_connection() as conn:
        row = conn.execute("SELECT failed_node, status, error_type FROM Tickets WHERE ticket_id = ?", (updates["ticket_id"],)).fetchone()
        assert row["failed_node"] == "diagnose"
        assert row["status"] == "open"
        assert row["error_type"] == "max_retries_exceeded"


def test_close_case_node():
    """Tests close_case terminal node."""
    state = create_initial_state()
    updates = close_case(state)
    assert updates["status"] == "closed"

    with get_db_connection() as conn:
        row = conn.execute("SELECT status FROM Crop_Cases WHERE case_id = 100").fetchone()
        assert row["status"] == "closed"


# ==============================================================================
# 4. Graph Assembly and Execution Tests (with MemorySaver Checkpointer)
# ==============================================================================

def test_build_crop_disease_graph_assembly():
    """Verifies build_crop_disease_graph compiles cleanly with MemorySaver."""
    mem = MemorySaver()
    graph = build_crop_disease_graph(checkpointer=mem)
    assert graph is not None
    assert "collect_crop_data" in graph.nodes
    assert "diagnose" in graph.nodes
    assert "propose_treatment" in graph.nodes
    assert "hitl_check" in graph.nodes
    assert "await_farmer_confirmation" in graph.nodes
    assert "execute_treatment" in graph.nodes
    assert "await_observation" in graph.nodes
    assert "evaluate_result" in graph.nodes
    assert "re_diagnose" in graph.nodes
    assert "handle_failure" in graph.nodes
    assert "close_case" in graph.nodes


@patch("agents.graphs.crop_disease.nodes.hybrid_search")
@patch("agents.graphs.crop_disease.nodes.self_rag_verify")
def test_full_workflow_happy_path_recovered(mock_verify, mock_search):
    """
    Tests complete end-to-end execution of the crop disease graph:
    1. Case ingested -> diagnosis (Neem Oil Extract, low hazard)
    2. Propose treatment -> hitl_check (no signoff needed)
    3. Interrupt at await_farmer_confirmation -> farmer confirms
    4. Execute treatment -> sprayer dispatched
    5. Interrupt at await_observation -> outcome 'recovered'
    6. Evaluate result -> close_case terminal state
    """
    mock_search.return_value = ["Powdery Mildew Treatment: Apply Neem Oil Extract."]
    mock_verify.return_value = MagicMock(is_relevant=True)

    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.invoke.return_value = DiagnosisResult(
        disease_name="Powdery Mildew",
        confidence=0.95,
        reasoning="Symptoms match powdery mildew exactly.",
        recommended_chemical_names=["Neem Oil Extract"],
    )
    mock_llm.with_structured_output.return_value = mock_structured

    mem = MemorySaver()
    graph = build_crop_disease_graph(llm=mock_llm, checkpointer=mem)
    thread_id = "thread_crop_happy_path_100"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = create_initial_state(
        case_id=100,
        thread_id=thread_id,
        report="Powdery white residue on wheat leaves.",
    )

    async def _run_workflow():
        # Run 1: Runs from START -> pauses at await_farmer_confirmation
        await graph.ainvoke(initial_state, config=config)
        snap1 = await graph.aget_state(config)
        assert len(snap1.tasks) > 0
        assert "await_farmer_confirmation" in snap1.next or any(t.name == "await_farmer_confirmation" for t in snap1.tasks)
        assert snap1.values.get("status") == "hitl_check"

        # Run 2: Resume with farmer confirmation -> dispatches sprayer -> pauses at await_observation
        await graph.ainvoke(Command(resume={"confirmed": True}), config=config)
        snap2 = await graph.aget_state(config)
        assert len(snap2.tasks) > 0
        assert "await_observation" in snap2.next or any(t.name == "await_observation" for t in snap2.tasks)
        assert snap2.values.get("status") == "treatment_started"
        assert snap2.values.get("dispatch_id") is not None

        # Run 3: Resume with observation recovered -> advances to close_case
        await graph.ainvoke(Command(resume={"outcome": "recovered", "notes": "Leaves fully recovered."}), config=config)
        snap3 = await graph.aget_state(config)
        assert len(snap3.tasks) == 0  # Graph finished
        assert snap3.values.get("status") == "closed"

    asyncio.run(_run_workflow())


@patch("agents.graphs.crop_disease.nodes.hybrid_search")
@patch("agents.graphs.crop_disease.nodes.self_rag_verify")
def test_full_workflow_hitl_approval_and_observation_loop(mock_verify, mock_search):
    """
    Tests end-to-end execution involving HITL sign-off and an observation loop:
    1. Ingestion -> diagnosis recommends Glyphosate (restricted, requires sign-off)
    2. Propose treatment -> pauses at hitl_check interrupt
    3. Admin approves -> advances to await_farmer_confirmation interrupt
    4. Farmer confirms -> executes treatment -> pauses at await_observation interrupt
    5. Observation 1: 'improved' -> loops back to await_observation interrupt
    6. Observation 2: 'recovered' -> evaluates -> close_case terminal state
    """
    mock_search.return_value = ["Aggressive weed infestation: Apply Glyphosate."]
    mock_verify.return_value = MagicMock(is_relevant=True)

    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_structured.invoke.return_value = DiagnosisResult(
        disease_name="Weed Infestation",
        confidence=0.98,
        reasoning="Severe weed overgrowth requires non-selective herbicide.",
        recommended_chemical_names=["Glyphosate"],
    )
    mock_llm.with_structured_output.return_value = mock_structured

    mem = MemorySaver()
    graph = build_crop_disease_graph(llm=mock_llm, checkpointer=mem)
    thread_id = "thread_crop_hitl_loop_200"
    config = {"configurable": {"thread_id": thread_id}}

    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO Crop_Cases (case_id, thread_id, customer_id, field_id, status, retry_count) "
            "VALUES (200, ?, 1, 1, 'case_created', 0)",
            (thread_id,),
        )
        conn.commit()

    initial_state = create_initial_state(
        case_id=200,
        thread_id=thread_id,
        report="Severe weed infestation threatening wheat yield.",
    )

    async def _run_hitl_workflow():
        # Step 1: Ingestion -> pauses at hitl_check
        await graph.ainvoke(initial_state, config=config)
        snap1 = await graph.aget_state(config)
        assert len(snap1.tasks) > 0
        assert "hitl_check" in snap1.next or any(t.name == "hitl_check" for t in snap1.tasks)
        assert snap1.values.get("status") == "propose_treatment"

        # Step 2: Admin approves HITL -> advances to await_farmer_confirmation
        await graph.ainvoke(Command(resume={"approved": True, "notes": "Approved for targeted weed control"}), config=config)
        snap2 = await graph.aget_state(config)
        assert len(snap2.tasks) > 0
        assert "await_farmer_confirmation" in snap2.next or any(t.name == "await_farmer_confirmation" for t in snap2.tasks)
        assert snap2.values.get("status") == "hitl_check"
        assert snap2.values.get("hitl_status") == "approved"

        # Step 3: Farmer confirms -> executes treatment -> pauses at await_observation
        await graph.ainvoke(Command(resume={"confirmed": True}), config=config)
        snap3 = await graph.aget_state(config)
        assert len(snap3.tasks) > 0
        assert "await_observation" in snap3.next or any(t.name == "await_observation" for t in snap3.tasks)
        assert snap3.values.get("status") == "treatment_started"

        # Step 4: Observation reports 'improved' -> loops back to await_observation
        await graph.ainvoke(Command(resume={"outcome": "improved", "notes": "Weeds withering but some remain."}), config=config)
        snap4 = await graph.aget_state(config)
        assert len(snap4.tasks) > 0
        assert "await_observation" in snap4.next or any(t.name == "await_observation" for t in snap4.tasks)
        assert snap4.values.get("status") == "improved"

        # Step 5: Final observation reports 'recovered' -> advances to close_case
        await graph.ainvoke(Command(resume={"outcome": "recovered", "notes": "Field completely cleared."}), config=config)
        snap5 = await graph.aget_state(config)
        assert len(snap5.tasks) == 0
        assert snap5.values.get("status") == "closed"

    asyncio.run(_run_hitl_workflow())


# ==============================================================================
# 5. Package Exports Test
# ==============================================================================

def test_crop_disease_package_exports():
    """Ensures all public symbols are correctly exported from agents.graphs.crop_disease."""
    import agents.graphs.crop_disease as crop_pkg

    assert hasattr(crop_pkg, "CaseState")
    assert hasattr(crop_pkg, "build_crop_disease_graph")
    assert hasattr(crop_pkg, "collect_crop_data")
    assert hasattr(crop_pkg, "make_diagnose_node")
    assert hasattr(crop_pkg, "propose_treatment")
    assert hasattr(crop_pkg, "hitl_check")
    assert hasattr(crop_pkg, "await_farmer_confirmation")
    assert hasattr(crop_pkg, "execute_treatment")
    assert hasattr(crop_pkg, "await_observation")
    assert hasattr(crop_pkg, "evaluate_result")
    assert hasattr(crop_pkg, "re_diagnose")
    assert hasattr(crop_pkg, "handle_failure")
    assert hasattr(crop_pkg, "close_case")
    assert hasattr(crop_pkg, "MAX_RETRIES")
    assert hasattr(crop_pkg, "DiagnosisResult")

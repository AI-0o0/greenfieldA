from __future__ import annotations

import json
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage

from mcp_server.tools import get_db_connection
from .state import CaseState

from pydantic import BaseModel, ConfigDict
from langchain_core.language_models.chat_models import BaseChatModel

from rag.retrievers import hybrid_search
from rag.verifier import self_rag_verify

from langgraph.types import interrupt

from schemas.tool_inputs import DispatchEquipmentInput as DispatchInput
from mcp_server.tools import dispatch_equipment

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _persist_case(state: CaseState, **fields) -> None:
    """
    Writes the given fields to the Crop_Cases row for this case.
    dict-typed fields are JSON-serialized before storage.
    Called at the end of every node so each meaningful transition
    is checkpointed to durable storage, not just to the in-memory
    LangGraph state.
    """
    if not fields:
        return

    json_fields = {"crop_data", "diagnosis", "proposed_treatment", "observation_result"}
    columns, values = [], []
    for key, value in fields.items():
        columns.append(f"{key} = ?")
        values.append(json.dumps(value) if key in json_fields and value is not None else value)

    values.append(_now())          # updated_at
    values.append(state["case_id"])  # WHERE clause

    conn = get_db_connection()
    try:
        conn.execute(
            f"UPDATE Crop_Cases SET {', '.join(columns)}, updated_at = ? WHERE case_id = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def collect_crop_data(state: CaseState) -> dict:
    """
    Entry node. Pulls the farmer-reported symptoms out of the most
    recent human message and stores them as structured crop_data.
    This is intentionally simple extraction (not LLM-parsed yet) —
    diagnose() is the node that reasons over this data with RAG.
    """
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    raw_report = last_human.content if last_human else ""

    crop_data = {
        "raw_report": raw_report,
        "customer_id": state["customer_id"],
        "field_id": state["field_id"],
        "reported_at": _now(),
    }

    updates = {
        "status": "collect_crop_data",
        "crop_data": crop_data,
        "retry_count": 0,   # reset at the start of a fresh diagnostic phase
    }

    _persist_case(state, **updates)

    return updates

class DiagnosisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disease_name: str
    confidence: float                     # 0.0-1.0
    reasoning: str
    recommended_chemical_names: list[str]  # names only; propose_treatment resolves these to chemical_id


DIAGNOSIS_SYSTEM = """You are an agricultural diagnostic assistant.
Diagnose the crop issue using ONLY the retrieved knowledge base context provided.
Do not rely on general knowledge outside the provided context.
If the context does not support a confident diagnosis, say so honestly in your
reasoning and lower your confidence score accordingly."""


def make_diagnose_node(llm: BaseChatModel):
    """
    Factory so the node can close over an llm instance, matching the
    dependency-injection pattern already used in decomposition.py
    (decompose_goal(goal, llm)) rather than instantiating a client
    inside the node itself.
    """

    def diagnose(state: CaseState) -> dict:
        crop_data = state["crop_data"]
        query = crop_data.get("raw_report", "")

        treatment_history = crop_data.get("treatment_history", [])
        if treatment_history:
            history_lines = []
            for attempt in treatment_history:
                treatment = attempt.get("proposed_treatment") or {}
                history_lines.append(
                    f"- Tried {treatment.get('chemical_name', 'unknown chemical')} "
                    f"-> outcome: {attempt.get('outcome', 'unknown')}"
                    + (f" (notes: {attempt['notes']})" if attempt.get("notes") else "")
                )
            query = (
                f"{query}\n\n"
                f"Prior treatment attempts on this case (most recent last):\n"
                + "\n".join(history_lines)
            )

        # --- Retrieval (same underlying RAG used by search_agricultural_knowledge,
        # called directly rather than through the MCP tool wrapper, since this is
        # server-side graph logic, not an MCP client round trip) ---
        chunks = hybrid_search(query, top_k=3)

        if not chunks:
            diagnosis = {
                "grounded": False,
                "reason": "no_knowledge_base_results",
            }
            updates = {
                "status": "diagnose",
                "rag_context": "",
                "diagnosis": diagnosis,
                "retry_count": state["retry_count"] + 1,
            }
            _persist_case(state, **updates)
            return updates

        rag_context = "\n---\n".join(chunks)

        verification = self_rag_verify(
            query=query,
            context=chunks,
            answer=rag_context,
        )

        if not verification.is_relevant:
            diagnosis = {
                "grounded": False,
                "reason": "self_rag_flagged_irrelevant",
            }
            updates = {
                "status": "diagnose",
                "rag_context": rag_context,
                "diagnosis": diagnosis,
                "retry_count": state["retry_count"] + 1,
            }
            _persist_case(state, **updates)
            return updates

        # --- Reasoning: LLM diagnosis constrained to the retrieved context ---
        result: DiagnosisResult = llm.with_structured_output(DiagnosisResult).invoke(
            [
                ("system", DIAGNOSIS_SYSTEM),
                (
                    "human",
                    f"Farmer-reported issue: {query!r}\n\n"
                    f"Retrieved knowledge base context:\n{rag_context}\n\n"
                    f"Provide a diagnosis grounded strictly in the context above.",
                ),
            ],
            temperature=0.1,
        )

        diagnosis = {
            "grounded": True,
            "disease_name": result.disease_name,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
            "recommended_chemical_names": result.recommended_chemical_names,
        }

        updates = {
            "status": "diagnose",
            "rag_context": rag_context,
            "diagnosis": diagnosis,
            "retry_count": 0,   # reset — this diagnostic attempt succeeded
        }
        _persist_case(state, **updates)
        return updates

    return diagnose

def propose_treatment(state: CaseState) -> dict:
    """
    Constrained ReAct node: the LLM's diagnosis already named candidate
    chemicals in plain text (recommended_chemical_names), but this node
    does NOT let the model invent a chemical_id or equipment_id freely.
    It resolves names against the real Chemicals table (the whitelist)
    and picks real, currently-idle Equipment — both DB-verified facts,
    not model guesses. This mirrors the same whitelist discipline
    dispatch_equipment() already enforces server-side.
    """
    diagnosis = state["diagnosis"]

    if not diagnosis.get("grounded"):
        # Should not normally be reached — the graph's conditional edge
        # should route ungrounded diagnoses back to diagnose/handle_failure
        # before this node runs. Defensive guard in case of a wiring bug.
        updates = {
            "status": "propose_treatment",
            "proposed_treatment": {"error": "diagnosis_not_grounded"},
        }
        _persist_case(state, **updates)
        return updates

    candidate_names = diagnosis.get("recommended_chemical_names", [])

    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # --- Resolve candidate names against the real whitelist (Chemicals table) ---
        chemical_row = None
        for name in candidate_names:
            cursor.execute(
                "SELECT chemical_id, name, hazard_class, requires_signoff "
                "FROM Chemicals WHERE name = ?",
                (name,),
            )
            row = cursor.fetchone()
            if row:
                chemical_row = row
                break  # first whitelist match wins

        if chemical_row is None:
            # None of the model's recommended names exist in the real
            # Chemicals table — this is a genuine failure, not something
            # a retry fixes on its own, since the model needs real data
            # to work from. Route to handle_failure via the graph edge.
            updates = {
                "status": "propose_treatment",
                "proposed_treatment": {
                    "error": "no_whitelisted_chemical_match",
                    "attempted_names": candidate_names,
                },
            }
            _persist_case(state, **updates)
            return updates

        # --- Pick idle sprayer equipment for this field's job ---
        cursor.execute(
            "SELECT equipment_id FROM Equipment "
            "WHERE equipment_type = 'sprayer' AND status = 'idle' "
            "ORDER BY equipment_id LIMIT 1"
        )
        equipment_row = cursor.fetchone()

        if equipment_row is None:
            updates = {
                "status": "propose_treatment",
                "proposed_treatment": {
                    "error": "no_idle_sprayer_available",
                    "chemical_id": chemical_row["chemical_id"],
                },
            }
            _persist_case(state, **updates)
            return updates

    finally:
        conn.close()

    proposed_treatment = {
        "chemical_id": chemical_row["chemical_id"],
        "chemical_name": chemical_row["name"],
        "hazard_class": chemical_row["hazard_class"],
        "equipment_id": equipment_row["equipment_id"],
        "field_id": state["field_id"],
        "customer_id": state["customer_id"],
        "job_type": "spray",
    }

    updates = {
        "status": "propose_treatment",
        "proposed_treatment": proposed_treatment,
        # hitl_required is derived straight from the whitelist data,
        # not decided by the model — hitl_check will read this table
        # value again itself before pausing, this is just a preview flag.
        "hitl_required": bool(chemical_row["requires_signoff"]),
    }
    _persist_case(state, **updates)
    return updates

def hitl_check(state: CaseState) -> dict:
    """
    Authoritative HITL gate. Re-reads Chemicals.requires_signoff directly
    from the DB (does not trust proposed_treatment's cached preview flag,
    in case the treatment was revised without re-running propose_treatment).

    If sign-off is required, this node:
      1. Writes a row to Crop_HITL_Tasks with the full state snapshot.
      2. Calls interrupt() — this pauses graph execution and persists
         the checkpoint. The graph process can be killed here and the
         run will resume from this exact point once the admin acts.
      3. On resume, interrupt() returns the value the platform passed
         in when it resumed the run (the admin's decision).

    This is the ONLY HITL pause for chemical sign-off in this graph.
    dispatch_equipment's own internal elicitation must be bypassed when
    called from execute_treatment, since approval already happened here.
    """
    proposed_treatment = state["proposed_treatment"]

    if proposed_treatment.get("error"):
        # Defensive guard — propose_treatment failed upstream, this
        # node shouldn't have been reached. Graph wiring should route
        # errors to handle_failure before hitl_check.
        return {
            "status": "hitl_check",
            "proposed_treatment": proposed_treatment,
        }

    chemical_id = proposed_treatment["chemical_id"]

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT requires_signoff FROM Chemicals WHERE chemical_id = ?",
            (chemical_id,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    requires_signoff = bool(row["requires_signoff"]) if row else False

    if not requires_signoff:
        updates = {
            "status": "hitl_check",
            "hitl_required": False,
            "hitl_status": None,
        }
        _persist_case(state, **updates)
        return updates

    # --- Sign-off required: open a Crop_HITL_Tasks row and pause ---
    import json # Added locally just in case it wasn't at the top
    state_snapshot = json.dumps(
        {
            "case_id": state["case_id"],
            "diagnosis": state["diagnosis"],
            "proposed_treatment": proposed_treatment,
        }
    )

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Crop_HITL_Tasks
                (case_id, node_name, reason, state_snapshot, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (
                state["case_id"],
                "hitl_check",
                f"Chemical '{proposed_treatment['chemical_name']}' "
                f"(hazard class: {proposed_treatment['hazard_class']}) "
                f"requires human sign-off before dispatch.",
                state_snapshot,
            ),
        )
        task_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    updates = {
        "status": "awaiting_hitl",
        "hitl_required": True,
        "hitl_status": "pending",
        "hitl_task_id": task_id,
    }
    _persist_case(state, **updates)

    # Pause here. The platform resumes this thread later with the
    # admin's decision, e.g. {"approved": True, "notes": "..."} or
    # {"approved": False, "notes": "..."}.
    admin_decision = interrupt(
        {
            "reason": "chemical_signoff_required",
            "task_id": task_id,
            "proposed_treatment": proposed_treatment,
        }
    )

    # --- Execution resumes here once the platform resumes the thread ---
    approved = bool(admin_decision.get("approved"))
    final_status = "approved" if approved else "rejected"

    conn = get_db_connection()
    try:
        conn.execute(
            "UPDATE Crop_HITL_Tasks SET status = ?, admin_notes = ?, "
            "resolved_at = ? WHERE task_id = ?",
            (final_status, admin_decision.get("notes"), _now(), task_id),
        )
        conn.commit()
    finally:
        conn.close()

    resumed_updates = {
        "status": "hitl_check",
        "hitl_status": final_status,
    }
    _persist_case(state, **resumed_updates)
    return resumed_updates

def await_farmer_confirmation(state: CaseState) -> dict:
    """
    Interrupt point: the graph genuinely pauses here until the farmer
    replies through the platform, which may take hours or days. Uses
    the same mid-node interrupt() pattern as hitl_check, but this is
    NOT a HITL admin approval — it's an external farmer response, so
    it does not touch Crop_HITL_Tasks at all.
    """
    proposed_treatment = state["proposed_treatment"]

    updates_before = {
        "status": "awaiting_farmer_confirmation",
    }
    _persist_case(state, **updates_before)

    # Pause here. The platform resumes this thread later with the
    # farmer's reply, e.g. {"confirmed": True} or {"confirmed": False}.
    farmer_response = interrupt(
        {
            "reason": "farmer_confirmation_required",
            "case_id": state["case_id"],
            "proposed_treatment": proposed_treatment,
            "prompt": (
                f"Proposed treatment: {proposed_treatment.get('chemical_name', 'unknown')} "
                f"applied via sprayer to field {state['field_id']}. Confirm to proceed?"
            ),
        }
    )

    # --- Execution resumes here once the platform resumes the thread ---
    confirmed = bool(farmer_response.get("confirmed"))

    updates_after = {
        "status": "farmer_confirmed" if confirmed else "closed",
        "farmer_confirmed": confirmed,
    }
    _persist_case(state, **updates_after)
    return updates_after

async def execute_treatment(state: CaseState) -> dict:
    """
    Calls the real dispatch_equipment tool directly (not through the MCP
    protocol) to actually dispatch the sprayer. pre_approved=True is
    passed unconditionally per team decision, since hitl_check already
    acted as the authoritative safety gate upstream. This node itself
    still guards against calling dispatch_equipment when that gate was
    never actually cleared, so a wiring bug can't silently skip sign-off.
    """
    proposed_treatment = state["proposed_treatment"]

    # Node-side guard: only proceed if hitl_check either wasn't required,
    # or was required and explicitly approved. This is the safety net
    # that replaces dispatch_equipment's own now-bypassed elicitation.
    if state.get("hitl_required") and state.get("hitl_status") != "approved":
        updates = {
            "status": "execute_treatment",
            "proposed_treatment": {
                **proposed_treatment,
                "error": "attempted_execution_without_hitl_approval",
            },
        }
        _persist_case(state, **updates)
        return updates

    dispatch_input = DispatchInput(
        equipment_id=proposed_treatment["equipment_id"],
        field_id=proposed_treatment["field_id"],
        job_type=proposed_treatment["job_type"],
        chemical_id=proposed_treatment["chemical_id"],
        customer_id=proposed_treatment["customer_id"],
    )

    try:
        result_message = await dispatch_equipment(
            dispatch_input,
            ctx=None,
            pre_approved=True,
        )
    except (ValueError, RuntimeError) as e:
        # Real tool-call failure (equipment no longer idle, ownership
        # mismatch, schema validation, etc.) — this is a genuine failure
        # a retry can't blindly fix, so it goes to handle_failure via
        # the graph's conditional edge, not a silent retry here.
        updates = {
            "status": "execute_treatment",
            "proposed_treatment": {
                **proposed_treatment,
                "error": "dispatch_failed",
                "error_detail": str(e),
            },
        }
        _persist_case(state, **updates)
        return updates

    # --- Success: pull the dispatch_id back out of Dispatch_Jobs ---
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT dispatch_id FROM Dispatch_Jobs "
            "WHERE equipment_id = ? AND field_id = ? "
            "ORDER BY dispatch_id DESC LIMIT 1",
            (proposed_treatment["equipment_id"], proposed_treatment["field_id"]),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    dispatch_id = row["dispatch_id"] if row else None

    updates = {
        "status": "treatment_started",
        "dispatch_id": dispatch_id,
    }
    _persist_case(state, **updates)
    return updates

def await_observation(state: CaseState) -> dict:
    """
    Interrupt point: pauses for days waiting on a follow-up observation
    of the treated crop (recovered / improved / worsened). Same mid-node
    interrupt() pattern as hitl_check and await_farmer_confirmation.

    Reached both on the first pass (after execute_treatment) and again
    on the "improved" loop-back from evaluate_result — continue_treatment
    routes straight back into this same node rather than a separate one,
    since the wait itself is identical regardless of which pass it is.
    """
    updates_before = {
        "status": "awaiting_observation",
    }
    _persist_case(state, **updates_before)

    # Pause here. The platform resumes this thread later with a new
    # follow-up observation, e.g. {"outcome": "recovered" | "improved" | "worsened",
    # "notes": Optional[str]}.
    observation = interrupt(
        {
            "reason": "treatment_observation_required",
            "case_id": state["case_id"],
            "dispatch_id": state.get("dispatch_id"),
            "prompt": "Report the current state of the crop following treatment.",
        }
    )

    # --- Execution resumes here once the platform resumes the thread ---
    outcome = observation.get("outcome")

    updates_after = {
        "status": "evaluate_result",
        "observation_result": {
            "outcome": outcome,
            "notes": observation.get("notes"),
            "observed_at": _now(),
        },
    }
    _persist_case(state, **updates_after)
    return updates_after

VALID_OUTCOMES = {"recovered", "improved", "worsened"}

def evaluate_result(state: CaseState) -> dict:
    """
    Branch point for the treatment-outcome loop. Validates the raw
    observation captured by await_observation, then sets status to one
    of three recognized outcomes for the graph's conditional edge to
    route on:
      recovered -> close_case
      improved  -> await_observation (loop, continue monitoring)
      worsened  -> re_diagnose -> diagnose (loop)

    A malformed/unrecognized outcome is NOT one of these three branches —
    it's routed to handle_failure via status="invalid_observation", since
    the graph cannot safely guess what the platform meant to report.
    """
    observation_result = state.get("observation_result") or {}
    outcome = observation_result.get("outcome")

    if outcome not in VALID_OUTCOMES:
        updates = {
            "status": "invalid_observation",
            "observation_result": {
                **observation_result,
                "error": "unrecognized_outcome",
                "received_value": outcome,
            },
        }
        _persist_case(state, **updates)
        return updates

    # status directly encodes the branch — the graph's conditional edge
    # reads this to route to close_case / await_observation / re_diagnose
    status_by_outcome = {
        "recovered": "recovered",
        "improved": "improved",
        "worsened": "worsened",
    }

    updates = {
        "status": status_by_outcome[outcome],
    }
    _persist_case(state, **updates)
    return updates

def re_diagnose(state: CaseState) -> dict:
    """
    Loop-back node reached when evaluate_result classifies the outcome
    as 'worsened'. Resets retry_count to 0 (this is a fresh diagnostic
    attempt, not a retry of the previous failed one) and routes back
    into diagnose with the new observation folded into crop_data so the
    next diagnosis has the full picture: original symptoms + what
    happened after the first treatment.
    """
    observation_result = state.get("observation_result") or {}
    crop_data = dict(state.get("crop_data") or {})

    # Append treatment history so diagnose() reasons over the full
    # picture, not just the original report as if nothing was tried yet.
    treatment_history = crop_data.get("treatment_history", [])
    treatment_history.append(
        {
            "proposed_treatment": state.get("proposed_treatment"),
            "outcome": observation_result.get("outcome"),
            "notes": observation_result.get("notes"),
            "observed_at": observation_result.get("observed_at"),
        }
    )
    crop_data["treatment_history"] = treatment_history

    updates = {
        "status": "re_diagnose",
        "crop_data": crop_data,
        "retry_count": 0,   # fresh diagnostic attempt, not a retry of the old one
    }
    _persist_case(state, **updates)
    return updates


MAX_RETRIES = 3

# Error markers this node knows how to recognize, in priority order.
# Each maps a state field to the node that produced it, so the ticket
# records which stage actually failed.
_ERROR_SOURCES = [
    ("observation_result", "evaluate_result"),
    ("proposed_treatment", "propose_treatment_or_execute_treatment"),
    ("diagnosis", "diagnose"),
]


def handle_failure(state: CaseState) -> dict:
    """
    Catches unplanned failures — a distinct code path from hitl_check.
    HITL is an expected pause for a decision the agent isn't allowed to
    make alone; this node is for failures nothing in the graph can
    resolve on its own: an unresolvable ungrounded diagnosis after
    retries are exhausted, a chemical/equipment lookup that came back
    empty, a dispatch_equipment call that raised, or a malformed
    observation from the platform.

    Opens a real Tickets row (status='open') with the state snapshot
    at the point of failure, and does NOT auto-retry — a human must
    resolve the ticket and resume the run from its checkpoint.
    """
    failed_node = "unknown"
    error_type = "unknown_error"
    error_message = "No specific error field found in state."

    for field_name, source_node in _ERROR_SOURCES:
        field_value = state.get(field_name) or {}
        if isinstance(field_value, dict) and field_value.get("error"):
            failed_node = source_node
            error_type = field_value["error"]
            error_message = field_value.get("error_detail") or field_value.get(
                "reason", field_value["error"]
            )
            break
    else:
        # No explicit error marker found — check whether this was
        # reached via exhausted retries in diagnose instead.
        if state.get("retry_count", 0) >= MAX_RETRIES:
            failed_node = "diagnose"
            error_type = "max_retries_exceeded"
            error_message = (
                f"diagnose failed to produce a grounded diagnosis after "
                f"{state['retry_count']} attempts."
            )

    import json # Added locally to ensure it is available
    state_snapshot = json.dumps(
        {
            "case_id": state.get("case_id"),
            "status": state.get("status"),
            "crop_data": state.get("crop_data"),
            "diagnosis": state.get("diagnosis"),
            "proposed_treatment": state.get("proposed_treatment"),
            "observation_result": state.get("observation_result"),
            "retry_count": state.get("retry_count"),
        }
    )

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO Tickets
                (thread_id, failed_node, error_type, error_message, state_snapshot, status)
            VALUES (?, ?, ?, ?, ?, 'open')
            """,
            (
                state["thread_id"],
                failed_node,
                error_type,
                error_message,
                state_snapshot,
            ),
        )
        ticket_id = cursor.lastrowid
        conn.commit()
    finally:
        conn.close()

    updates = {
        "status": "failed",
        "ticket_id": ticket_id,
        "ticket_status": "open",
    }
    _persist_case(state, **updates)

    # No interrupt() here — unlike HITL, a ticket doesn't pause execution
    # waiting for a specific decision shape. The graph simply ends this
    # run at status="failed"; the platform resumes the thread once an
    # admin resolves the ticket, re-entering at the failed_node.
    return updates

def close_case(state: CaseState) -> dict:
    """
    Terminal node for every path that ends the case successfully or
    by farmer decline: recovered treatment, or a declined confirmation
    routed here from the graph's conditional edge. Purely a status
    write — no further branching happens after this node.
    """
    updates = {
        "status": "closed",
    }
    _persist_case(state, **updates)
    return updates


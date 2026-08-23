from __future__ import annotations

import os

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.language_models.chat_models import BaseChatModel

from .state import CaseState
from .nodes import (
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
)


# ==============================================================
# Conditional edge routing functions
# Each reads state written by the node it follows and returns the
# name of the next node to run.
# ==============================================================

def route_after_diagnose(state: CaseState) -> str:
    diagnosis = state.get("diagnosis") or {}
    if diagnosis.get("grounded"):
        return "propose_treatment"
    if state.get("retry_count", 0) >= MAX_RETRIES:
        return "handle_failure"
    return "diagnose"  # loop back for another attempt


def route_after_propose_treatment(state: CaseState) -> str:
    proposed_treatment = state.get("proposed_treatment") or {}
    if proposed_treatment.get("error"):
        return "handle_failure"
    return "hitl_check"


def route_after_hitl_check(state: CaseState) -> str:
    if state.get("hitl_status") == "rejected":
        return "propose_treatment"  # revise and re-submit
    return "await_farmer_confirmation"  # approved or sign-off not required


def route_after_farmer_confirmation(state: CaseState) -> str:
    if state.get("status") == "declined":
        return "close_case"
    return "execute_treatment"  # status == "farmer_confirmed"


def route_after_execute_treatment(state: CaseState) -> str:
    proposed_treatment = state.get("proposed_treatment") or {}
    if proposed_treatment.get("error"):
        return "handle_failure"
    return "await_observation"


def route_after_evaluate_result(state: CaseState) -> str:
    status = state.get("status")
    if status == "recovered":
        return "close_case"
    if status == "improved":
        return "await_observation"  # keep monitoring
    if status == "worsened":
        return "re_diagnose"
    return "handle_failure"  # status == "invalid_observation"


# ==============================================================
# Graph assembly
# ==============================================================

def build_crop_disease_graph(llm: BaseChatModel):
    """
    Builds and compiles the Crop Disease Treatment state graph, wired
    to a durable SQLite checkpointer on the same farm.db used by the
    rest of the system. Call this once per process; reuse the
    compiled graph object across invocations/resumes.
    """
    diagnose = make_diagnose_node(llm)

    builder = StateGraph(CaseState)

    builder.add_node("collect_crop_data", collect_crop_data)
    builder.add_node("diagnose", diagnose)
    builder.add_node("propose_treatment", propose_treatment)
    builder.add_node("hitl_check", hitl_check)
    builder.add_node("await_farmer_confirmation", await_farmer_confirmation)
    builder.add_node("execute_treatment", execute_treatment)
    builder.add_node("await_observation", await_observation)
    builder.add_node("evaluate_result", evaluate_result)
    builder.add_node("re_diagnose", re_diagnose)
    builder.add_node("handle_failure", handle_failure)
    builder.add_node("close_case", close_case)

    builder.add_edge(START, "collect_crop_data")
    builder.add_edge("collect_crop_data", "diagnose")

    builder.add_conditional_edges(
        "diagnose",
        route_after_diagnose,
        {
            "propose_treatment": "propose_treatment",
            "diagnose": "diagnose",
            "handle_failure": "handle_failure",
        },
    )

    builder.add_conditional_edges(
        "propose_treatment",
        route_after_propose_treatment,
        {
            "hitl_check": "hitl_check",
            "handle_failure": "handle_failure",
        },
    )

    builder.add_conditional_edges(
        "hitl_check",
        route_after_hitl_check,
        {
            "propose_treatment": "propose_treatment",
            "await_farmer_confirmation": "await_farmer_confirmation",
        },
    )

    builder.add_conditional_edges(
        "await_farmer_confirmation",
        route_after_farmer_confirmation,
        {
            "close_case": "close_case",
            "execute_treatment": "execute_treatment",
        },
    )

    builder.add_conditional_edges(
        "execute_treatment",
        route_after_execute_treatment,
        {
            "await_observation": "await_observation",
            "handle_failure": "handle_failure",
        },
    )

    builder.add_edge("await_observation", "evaluate_result")

    builder.add_conditional_edges(
        "evaluate_result",
        route_after_evaluate_result,
        {
            "close_case": "close_case",
            "await_observation": "await_observation",
            "re_diagnose": "re_diagnose",
            "handle_failure": "handle_failure",
        },
    )

    builder.add_edge("re_diagnose", "diagnose")

    builder.add_edge("handle_failure", END)
    builder.add_edge("close_case", END)

    db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "db"))
    db_path = os.environ.get("GREENFIELD_DB_PATH") or os.path.join(db_dir, "farm.db")

    # SqliteSaver manages its own checkpoint tables inside the same
    # farm.db file — it does not touch or conflict with Crop_Cases,
    # Dispatch_Jobs, etc. This is what makes crash-and-resume work:
    # every node's returned state update is checkpointed here after
    # each transition, not just at run end.
    checkpointer_cm = SqliteSaver.from_conn_string(db_path)
    checkpointer = checkpointer_cm.__enter__()  # kept open for process lifetime

    graph = builder.compile(checkpointer=checkpointer)
    return graph
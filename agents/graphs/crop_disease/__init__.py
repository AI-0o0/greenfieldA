"""
agents/graphs/crop_disease/__init__.py

Greenfield Crop Disease State Graph Agent Package.
Provides exports for the CaseState schema, node handlers, routing conditions,
and graph factory.
"""

from agents.graphs.crop_disease.state import CaseState
from agents.graphs.crop_disease.nodes import (
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
    DiagnosisResult,
)
from agents.graphs.crop_disease.graph import (
    build_crop_disease_graph,
    route_after_diagnose,
    route_after_propose_treatment,
    route_after_hitl_check,
    route_after_farmer_confirmation,
    route_after_execute_treatment,
    route_after_evaluate_result,
)
from agents.graphs.crop_disease.runner import (
    run_crop_turn,
    resume_crop_interrupt,
    resolve_crop_ticket_and_resume,
    get_crop_agent,
    ensure_case_row,
    list_crop_hitl_tasks,
    get_crop_hitl_task,
    new_thread_id,
)

__all__ = [
    "CaseState",
    "collect_crop_data",
    "make_diagnose_node",
    "propose_treatment",
    "hitl_check",
    "await_farmer_confirmation",
    "execute_treatment",
    "await_observation",
    "evaluate_result",
    "re_diagnose",
    "handle_failure",
    "close_case",
    "MAX_RETRIES",
    "DiagnosisResult",
    "build_crop_disease_graph",
    "route_after_diagnose",
    "route_after_propose_treatment",
    "route_after_hitl_check",
    "route_after_farmer_confirmation",
    "route_after_execute_treatment",
    "route_after_evaluate_result",
    "run_crop_turn",
    "resume_crop_interrupt",
    "resolve_crop_ticket_and_resume",
    "get_crop_agent",
    "ensure_case_row",
    "list_crop_hitl_tasks",
    "get_crop_hitl_task",
    "new_thread_id",
]

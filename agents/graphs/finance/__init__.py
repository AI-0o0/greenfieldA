"""
agents/graphs/finance/__init__.py

Greenfield Autonomous Finance & Lending State Graph Agent Package.
Provides clean modular exports for state schemas, database layer, durable checkpointers,
HITL escalation policies, failure ticket recovery, node handlers, and graph factories.
"""

from agents.graphs.finance.state import (
    FinanceState,
    RouteDecision,
    SpecialistDecision,
    GeneratedOptions,
    EligibilityEvaluation,
    DocumentValidation,
    FinancialAnalysisResult,
    AlternativeOptionsResult,
)
from agents.graphs.finance.db import (
    get_db_connection,
    serialize_state_for_db,
    fetch_farmer_db_profile,
)
from agents.graphs.finance.checkpointer import (
    get_sqlite_checkpointer,
)
from agents.graphs.finance.hitl import (
    evaluate_hitl_policy,
    create_or_update_hitl_task,
    fetch_pending_hitl_tasks,
    get_hitl_task,
    resume_hitl_task,
)
from agents.graphs.finance.tickets import (
    NodeExecutionError,
    record_failure_ticket,
    fetch_tickets,
    get_ticket,
    update_ticket_status,
    resolve_ticket_and_resume,
    safe_node_execute,
)
from agents.graphs.finance.nodes import (
    farmer_request_node,
    route_request_node,
    advice_node,
    collect_context_node,
    equipment_agent_node,
    crop_agent_node,
    generate_options_node,
    tot_advice_node,
    rag_policies_node,
    react_policies_node,
    generate_recommendation_node,
    financing_node,
    check_eligibility_node,
    rag_eligibility_node,
    react_eligibility_node,
    explain_rejection_node,
    collect_documents_node,
    wait_farmer_node,
    validate_documents_node,
    assess_financing_need_node,
    tot_financing_node,
    admin_review_node,
    submit_financing_node,
    wait_provider_node,
    provider_rejected_node,
    farmer_confirmation_node,
    generate_alternatives_node,
    process_financing_node,
    verify_transaction_node,
)
from agents.graphs.finance.resources import (
    SUBSIDY_PROGRAMS,
    UNDERWRITING_RULES,
    FINANCIAL_PRODUCTS,
    HITL_THRESHOLDS,
    lookup_financial_policies,
    get_all_financial_resources,
)
from agents.graphs.finance.tools import (
    lookup_policy_rules,
    calculate_loan_quote,
    calculate_dscr,
    check_farmer_eligibility_covenants,
    compare_financing_structures,
    FINANCE_TOOL_DISPATCH,
    FINANCE_TOOL_SCHEMAS,
)
from agents.graphs.finance.react_agent import (
    run_finance_react_agent,
    build_finance_step_model,
    build_finance_system_prompt,
)
from agents.graphs.finance.graph import (
    build_finance_graph,
    create_finance_agent,
    run_finance_turn,
)

__all__ = [
    # State & Pydantic Schemas
    "FinanceState",
    "RouteDecision",
    "SpecialistDecision",
    "GeneratedOptions",
    "EligibilityEvaluation",
    "DocumentValidation",
    "FinancialAnalysisResult",
    "AlternativeOptionsResult",
    # Database Helpers
    "get_db_connection",
    "serialize_state_for_db",
    "fetch_farmer_db_profile",
    # Checkpointing
    "get_sqlite_checkpointer",
    # HITL Management
    "evaluate_hitl_policy",
    "create_or_update_hitl_task",
    "fetch_pending_hitl_tasks",
    "get_hitl_task",
    "resume_hitl_task",
    # Ticket & Error Recovery
    "NodeExecutionError",
    "record_failure_ticket",
    "fetch_tickets",
    "get_ticket",
    "update_ticket_status",
    "resolve_ticket_and_resume",
    "safe_node_execute",
    # Nodes (including Constrained ReAct Agent nodes)
    "farmer_request_node",
    "route_request_node",
    "advice_node",
    "collect_context_node",
    "equipment_agent_node",
    "crop_agent_node",
    "generate_options_node",
    "tot_advice_node",
    "rag_policies_node",
    "react_policies_node",
    "generate_recommendation_node",
    "financing_node",
    "check_eligibility_node",
    "rag_eligibility_node",
    "react_eligibility_node",
    "explain_rejection_node",
    "collect_documents_node",
    "wait_farmer_node",
    "validate_documents_node",
    "assess_financing_need_node",
    "tot_financing_node",
    "admin_review_node",
    "submit_financing_node",
    "wait_provider_node",
    "provider_rejected_node",
    "farmer_confirmation_node",
    "generate_alternatives_node",
    "process_financing_node",
    "verify_transaction_node",
    # Resources & Tools
    "SUBSIDY_PROGRAMS",
    "UNDERWRITING_RULES",
    "FINANCIAL_PRODUCTS",
    "HITL_THRESHOLDS",
    "lookup_financial_policies",
    "get_all_financial_resources",
    "lookup_policy_rules",
    "calculate_loan_quote",
    "calculate_dscr",
    "check_farmer_eligibility_covenants",
    "compare_financing_structures",
    "FINANCE_TOOL_DISPATCH",
    "FINANCE_TOOL_SCHEMAS",
    # ReAct Engine
    "run_finance_react_agent",
    "build_finance_step_model",
    "build_finance_system_prompt",
    # Graph Engine & Execution
    "build_finance_graph",
    "create_finance_agent",
    "run_finance_turn",
]

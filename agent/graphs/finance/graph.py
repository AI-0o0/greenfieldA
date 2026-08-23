"""
agent/graphs/finance/graph.py

LangGraph StateGraph assembly and turn execution engine for the Greenfield
Autonomous Finance Agent.

Topology strictly implements the state machine in finance_graph.mmd, featuring:
- Cyclic document validation and remediation loops
- Dynamic interrupts for Farmer Document Upload, Senior Admin HITL, External Provider, and Farmer Acceptance
- Durable SQLite Checkpointing across process restarts
- Mid-node unplanned failure ticket tracking and checkpoint resumption
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agent.graphs.finance.state import FinanceState
from agent.graphs.finance.checkpointer import get_sqlite_checkpointer
from agent.graphs.finance.tickets import safe_node_execute, NodeExecutionError
from agent.graphs.finance.nodes import (
    farmer_request_node,
    route_request_node,
    route_request_condition,
    advice_node,
    collect_context_node,
    specialist_condition,
    equipment_agent_node,
    crop_agent_node,
    generate_options_node,
    tot_advice_node,
    rag_policies_node,
    generate_recommendation_node,
    financing_node,
    check_eligibility_node,
    rag_eligibility_node,
    eligible_condition,
    explain_rejection_node,
    collect_documents_node,
    wait_farmer_node,
    validate_documents_node,
    documents_valid_condition,
    assess_financing_need_node,
    tot_financing_node,
    hitl_condition,
    admin_review_node,
    admin_decision_condition,
    submit_financing_node,
    wait_provider_node,
    provider_response_condition,
    provider_rejected_node,
    farmer_confirmation_node,
    farmer_accepts_condition,
    farmer_accept_condition,
    generate_alternatives_node,
    process_financing_node,
    verify_transaction_node,
)


def build_finance_graph(
    checkpointer: Optional[Any] = None,
    interrupt_nodes: Optional[List[str]] = None,
    llm: Optional[BaseChatModel] = None,
) -> Any:
    """
    Builds and compiles the Greenfield Autonomous Finance Graph with safe node wrappers,
    conditional branch routers, and interrupt boundaries.
    """
    workflow = StateGraph(FinanceState)

    # 1. Register all nodes with safe execution wrapper
    workflow.add_node("farmer_request", lambda s: safe_node_execute("farmer_request", farmer_request_node, s, llm=llm))
    workflow.add_node("route_request", lambda s: safe_node_execute("route_request", route_request_node, s, llm=llm))

    # Advice Nodes
    workflow.add_node("advice", lambda s: safe_node_execute("advice", advice_node, s, llm=llm))
    workflow.add_node("collect_context", lambda s: safe_node_execute("collect_context", collect_context_node, s, llm=llm))
    workflow.add_node("equipment_agent", lambda s: safe_node_execute("equipment_agent", equipment_agent_node, s, llm=llm))
    workflow.add_node("crop_agent", lambda s: safe_node_execute("crop_agent", crop_agent_node, s, llm=llm))
    workflow.add_node("generate_options", lambda s: safe_node_execute("generate_options", generate_options_node, s, llm=llm))
    workflow.add_node("tot_advice", lambda s: safe_node_execute("tot_advice", tot_advice_node, s, llm=llm))
    workflow.add_node("rag_policies", lambda s: safe_node_execute("rag_policies", rag_policies_node, s, llm=llm))
    workflow.add_node("recommend", lambda s: safe_node_execute("recommend", generate_recommendation_node, s, llm=llm))

    # Financing Nodes
    workflow.add_node("financing", lambda s: safe_node_execute("financing", financing_node, s, llm=llm))
    workflow.add_node("check_eligibility", lambda s: safe_node_execute("check_eligibility", check_eligibility_node, s, llm=llm))
    workflow.add_node("rag_eligibility", lambda s: safe_node_execute("rag_eligibility", rag_eligibility_node, s, llm=llm))
    workflow.add_node("explain_rejection", lambda s: safe_node_execute("explain_rejection", explain_rejection_node, s, llm=llm))
    workflow.add_node("collect_documents", lambda s: safe_node_execute("collect_documents", collect_documents_node, s, llm=llm))
    workflow.add_node("wait_farmer", lambda s: safe_node_execute("wait_farmer", wait_farmer_node, s, llm=llm))
    workflow.add_node("validate_documents", lambda s: safe_node_execute("validate_documents", validate_documents_node, s, llm=llm))
    workflow.add_node("financial_analysis", lambda s: safe_node_execute("financial_analysis", assess_financing_need_node, s, llm=llm))
    workflow.add_node("tot_financing", lambda s: safe_node_execute("tot_financing", tot_financing_node, s, llm=llm))
    workflow.add_node("admin_review", lambda s: safe_node_execute("admin_review", admin_review_node, s, llm=llm))
    workflow.add_node("submit_financing", lambda s: safe_node_execute("submit_financing", submit_financing_node, s, llm=llm))
    workflow.add_node("wait_provider", lambda s: safe_node_execute("wait_provider", wait_provider_node, s, llm=llm))
    workflow.add_node("provider_rejected", lambda s: safe_node_execute("provider_rejected", provider_rejected_node, s, llm=llm))
    workflow.add_node("farmer_confirm", lambda s: safe_node_execute("farmer_confirm", farmer_confirmation_node, s, llm=llm))
    workflow.add_node("generate_alternatives", lambda s: safe_node_execute("generate_alternatives", generate_alternatives_node, s, llm=llm))
    workflow.add_node("process_financing", lambda s: safe_node_execute("process_financing", process_financing_node, s, llm=llm))
    workflow.add_node("verify_transaction", lambda s: safe_node_execute("verify_transaction", verify_transaction_node, s, llm=llm))

    # 2. Add Edges & Conditional Routing
    workflow.add_edge(START, "farmer_request")
    workflow.add_edge("farmer_request", "route_request")

    workflow.add_conditional_edges(
        "route_request",
        route_request_condition,
        {
            "advice": "advice",
            "financing": "financing",
        },
    )

    # Financial Advice Pathway Edges
    workflow.add_edge("advice", "collect_context")
    workflow.add_conditional_edges(
        "collect_context",
        specialist_condition,
        {
            "equipment": "equipment_agent",
            "crop": "crop_agent",
            "no": "generate_options",
        },
    )
    workflow.add_edge("equipment_agent", "generate_options")
    workflow.add_edge("crop_agent", "generate_options")
    workflow.add_edge("generate_options", "tot_advice")
    workflow.add_edge("tot_advice", "rag_policies")
    workflow.add_edge("rag_policies", "recommend")
    workflow.add_edge("recommend", END)

    # Financing Application Pathway Edges
    workflow.add_edge("financing", "check_eligibility")
    workflow.add_edge("check_eligibility", "rag_eligibility")
    workflow.add_conditional_edges(
        "rag_eligibility",
        eligible_condition,
        {
            "eligible": "collect_documents",
            "rejected": "explain_rejection",
        },
    )
    workflow.add_edge("explain_rejection", END)

    workflow.add_edge("collect_documents", "wait_farmer")
    workflow.add_edge("wait_farmer", "validate_documents")
    workflow.add_conditional_edges(
        "validate_documents",
        documents_valid_condition,
        {
            "valid": "financial_analysis",
            "invalid": "collect_documents",
        },
    )

    workflow.add_edge("financial_analysis", "tot_financing")
    workflow.add_conditional_edges(
        "tot_financing",
        hitl_condition,
        {
            "admin": "admin_review",
            "submit": "submit_financing",
        },
    )

    workflow.add_conditional_edges(
        "admin_review",
        admin_decision_condition,
        {
            "approve": "submit_financing",
            "reject": "explain_rejection",
            "more_info": "collect_documents",
        },
    )

    workflow.add_edge("submit_financing", "wait_provider")
    workflow.add_conditional_edges(
        "wait_provider",
        provider_response_condition,
        {
            "approved": "farmer_confirm",
            "rejected": "provider_rejected",
            "more_info": "collect_documents",
        },
    )

    workflow.add_edge("provider_rejected", "generate_alternatives")
    workflow.add_edge("generate_alternatives", "recommend")

    workflow.add_conditional_edges(
        "farmer_confirm",
        farmer_accept_condition,
        {
            "process": "process_financing",
            "alternative": "generate_alternatives",
        },
    )

    workflow.add_edge("process_financing", "verify_transaction")
    workflow.add_edge("verify_transaction", END)

    # Compile with checkpointer and interrupts
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_nodes,
    )


def create_finance_agent(
    checkpointer: Optional[Any] = None,
    interactive: bool = True,
    llm: Optional[BaseChatModel] = None,
    persistent: bool = False,
    db_path: Optional[str] = None,
) -> Any:
    """
    Factory to create compiled interactive finance graph with durable SQLite persistence support.
    """
    if checkpointer is not None:
        cp = checkpointer
    elif persistent:
        cp = get_sqlite_checkpointer(db_path=db_path)
    elif interactive:
        cp = MemorySaver()
    else:
        cp = None

    interrupts = ["wait_farmer", "admin_review", "wait_provider", "farmer_confirm"] if interactive else None
    return build_finance_graph(checkpointer=cp, interrupt_nodes=interrupts, llm=llm)


def run_finance_turn(
    graph: Any,
    thread_id: str,
    state_input: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Executes or resumes a turn on the finance graph for a given thread_id.
    Ensures thread_id is persisted into state and returns the updated state snapshot.
    If an unplanned mid-node failure occurs, catches NodeExecutionError and returns state with ticket info.
    """
    config = {"configurable": {"thread_id": thread_id}}
    input_payload = dict(state_input or {})
    if "thread_id" not in input_payload:
        input_payload["thread_id"] = thread_id

    try:
        state_snap = graph.get_state(config)
        if state_snap.next:
            if input_payload:
                graph.update_state(config, input_payload)
            return graph.invoke(None, config=config)
        else:
            return graph.invoke(input_payload, config=config)
    except NodeExecutionError as nerr:
        state_snap = graph.get_state(config)
        values = dict(state_snap.values or {})
        values.update({
            "error": str(nerr),
            "failed_node": nerr.node_name,
            "ticket_id": nerr.ticket_id,
        })
        return values

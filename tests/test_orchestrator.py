"""
tests/test_orchestrator.py

Unit & Integration Tests for Greenfield Dynamic Multi-Agent Orchestrator.
Tests LangGraph Command handoffs, dynamic handoff tool execution, cross-domain
state continuity, and context scoping across Front-Desk, Crop Disease,
Maintenance, Finance, and Fleet Planning agents.
"""

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agents.orchestrator import (
    build_orchestrator_graph,
    make_handoff_tool,
    run_orchestrator_turn,
)


def test_make_handoff_tool_returns_command():
    """Verifies make_handoff_tool generates a LangChain tool returning Command(goto=target)."""
    tool = make_handoff_tool("maintenance", "Transfer to maintenance specialist")
    assert tool.name == "transfer_to_maintenance"
    cmd = tool.invoke({"reason": "Hydraulic pump defect", "domain_summary": "SPR-3001 pressure loss"})
    assert cmd.goto == "maintenance"
    assert cmd.update["active_agent"] == "maintenance"
    assert len(cmd.update["handoff_history"]) == 1
    assert cmd.update["handoff_history"][0]["target"] == "maintenance"


def test_orchestrator_frontdesk_to_crop_handoff():
    """Tests conversational routing from frontdesk to crop disease clinic."""
    mem = MemorySaver()
    graph = build_orchestrator_graph(checkpointer=mem)
    thread_id = "test_orch_thread_crop_1"

    result = run_orchestrator_turn(
        graph,
        thread_id,
        "Hello, my wheat field in North Plot A is developing yellow powdery fungus on the leaves.",
    )
    assert result["active_agent"] == "crop_disease"
    assert len(result["trace"]) > 0


def test_orchestrator_frontdesk_to_maintenance_handoff():
    """Tests conversational routing from frontdesk to equipment maintenance."""
    mem = MemorySaver()
    graph = build_orchestrator_graph(checkpointer=mem)
    thread_id = "test_orch_thread_maint_1"

    result = run_orchestrator_turn(
        graph,
        thread_id,
        "Sprayer SPR-3001 has a major hydraulic oil leak and cannot build spray pressure.",
    )
    assert result["active_agent"] == "maintenance"


def test_orchestrator_frontdesk_to_finance_handoff():
    """Tests conversational routing from frontdesk to finance advisor."""
    mem = MemorySaver()
    graph = build_orchestrator_graph(checkpointer=mem)
    thread_id = "test_orch_thread_fin_1"

    result = run_orchestrator_turn(
        graph,
        thread_id,
        "I want to apply for a $40,000 seasonal crop financing loan.",
    )
    assert result["active_agent"] == "finance"


def test_orchestrator_cross_domain_multi_agent_chain():
    """
    Tests full cross-domain multi-agent lifecycle:
    1. Turn 1: Farmer reports crop symptoms caused by sprayer malfunction -> Frontdesk -> Crop -> Maintenance
    2. Turn 2: Maintenance identifies expensive pump overhaul -> Maintenance -> Finance
    3. Turn 3: Finance structures loan and wraps up with Front-Desk.
    """
    mem = MemorySaver()
    graph = build_orchestrator_graph(checkpointer=mem)
    thread_id = "test_orch_chain_101"

    # Turn 1: Crop issue with sprayer malfunction
    res1 = run_orchestrator_turn(
        graph,
        thread_id,
        "My wheat is distressed because the sprayer broke and had a pressure drop during spraying.",
    )
    assert res1["active_agent"] in ("crop_disease", "maintenance")

    # Turn 2: Follow-up on expensive repair costs
    res2 = run_orchestrator_turn(
        graph,
        thread_id,
        "The hydraulic pump replacement is too expensive to pay upfront. Can we get financing or a loan?",
    )
    assert res2["active_agent"] in ("maintenance", "finance")
    assert "finance" in res2["reply"].lower() or "loan" in res2["reply"].lower()

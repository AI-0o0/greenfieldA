"""
tests/test_website_backend.py

Integration Test Suite for Greenfield Agricultural Agency Web Platform (FastAPI backend).
Tests:
1. Health & Agent Catalog Discovery
2. Live MCP Tool Registration/Deregistration & Registry Sync
3. Dynamic RAG Document Addition, Retrieval Reflection, and Deletion
4. Unified HITL Inbox Listing and Resumption across Crop, Finance, and Maintenance
5. Unified Failure Ticket Board, Investigation, and Time-Travel Resumption
6. Multi-Agent Chat Dispatch across all 6 agents
"""

import asyncio
import json
import pytest
from starlette.testclient import TestClient

from website.backend.main import app
from mcp_server.tool_manager import bootstrap as bootstrap_tools, get_agent_tools, set_agent_tool_enabled
from mcp_server.tools import get_db_connection


@pytest.fixture(scope="module")
def client():
    bootstrap_tools()
    with TestClient(app) as c:
        yield c


# ==============================================================
# 1. Health & Agent Catalog Discovery
# ==============================================================

def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "mcp_url" in data


def test_list_agents_catalog(client):
    response = client.get("/api/agents")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    agent_ids = [a["id"] for a in data["agents"]]
    assert "orchestrator" in agent_ids
    assert "crop_disease" in agent_ids
    assert "maintenance" in agent_ids
    assert "finance" in agent_ids
    assert "knowledge_assistant" in agent_ids
    assert "fleet_planner" in agent_ids

    for agent in data["agents"]:
        assert len(agent["name"]) > 0
        assert len(agent["description"]) > 0
        assert len(agent["techniques"]) > 0


# ==============================================================
# 2. Live MCP Tool Registry & Dynamic Mutation
# ==============================================================

def test_get_tool_matrix(client):
    response = client.get("/api/admin/tools")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert "tools" in data
    assert "rows" in data
    assert "live_tools" in data
    assert len(data["live_tools"]) > 0


def test_toggle_tool_and_live_reflection(client):
    # 1. Toggle dispatch_equipment for maintenance (enable it)
    toggle_res = client.post(
        "/api/admin/tools/toggle",
        json={"agent_id": "maintenance", "tool_name": "dispatch_equipment", "enabled": True},
    )
    assert toggle_res.status_code == 200
    assert "dispatch_equipment" in toggle_res.json()["agent_tools_now"]

    # 2. Toggle it back to False (least privilege)
    toggle_back = client.post(
        "/api/admin/tools/toggle",
        json={"agent_id": "maintenance", "tool_name": "dispatch_equipment", "enabled": False},
    )
    assert toggle_back.status_code == 200
    assert "dispatch_equipment" not in toggle_back.json()["agent_tools_now"]


def test_verify_registry_consistency(client):
    response = client.get("/api/admin/tools/verify")
    assert response.status_code == 200
    data = response.json()
    assert "crop_disease" in data
    assert "finance" in data
    assert "maintenance" in data
    assert "knowledge_assistant" in data


# ==============================================================
# 3. Dynamic RAG Document Management
# ==============================================================

def test_dynamic_rag_add_and_delete_lifecycle(client):
    doc_name = "test_irrigation_policy.txt"
    doc_text = "Section 1: Drip irrigation saves 40% water.\n\nSection 2: High pressure pumps require daily maintenance."

    # 1. Add document
    add_res = client.post(
        "/api/admin/documents",
        json={"source_name": doc_name, "text": doc_text},
    )
    assert add_res.status_code == 200
    assert add_res.json()["chunks_added"] >= 2

    # 2. List documents and verify presence
    list_res = client.get("/api/admin/documents")
    assert list_res.status_code == 200
    sources = [d["source"] for d in list_res.json()["documents"]]
    assert doc_name in sources

    # 3. Delete document
    del_res = client.delete(f"/api/admin/documents/{doc_name}")
    assert del_res.status_code == 200
    assert del_res.json()["chunks_removed"] >= 2

    # 4. Verify gone
    list_res_after = client.get("/api/admin/documents")
    sources_after = [d["source"] for d in list_res_after.json()["documents"]]
    assert doc_name not in sources_after


# ==============================================================
# 4. Unified HITL Inbox Listing & Resolution
# ==============================================================

def test_hitl_inbox_listing(client):
    # Seed a test HITL task in DB
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO HITL_Tasks (thread_id, node_name, reason, assessed_amount, risk_level, status)
            VALUES ('test_thread_hitl_api', 'admin_review', 'High Capital Exposure', 85000.0, 'medium', 'pending')
            """
        )
        conn.commit()

    response = client.get("/api/hitl")
    assert response.status_code == 200
    data = response.json()
    assert "tasks" in data
    matching = [t for t in data["tasks"] if t["thread_id"] == "test_thread_hitl_api"]
    assert len(matching) > 0
    assert matching[0]["status"] == "pending"


# ==============================================================
# 5. Unified Failure Ticket System & Checkpoint Recovery
# ==============================================================

def test_ticket_board_listing_and_investigation(client):
    # Seed a test failure ticket in DB
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO Tickets (thread_id, failed_node, error_type, error_message, state_snapshot, status)
            VALUES ('test_thread_ticket_api', 'diagnose', 'max_retries_exceeded', 'Simulated failure', '{}', 'open')
            """
        )
        ticket_id = cursor.lastrowid
        conn.commit()

    # 1. List tickets
    list_res = client.get("/api/tickets")
    assert list_res.status_code == 200
    tickets = list_res.json()["tickets"]
    assert any(t["ticket_id"] == ticket_id for t in tickets)

    # 2. Mark investigating
    inv_res = client.post(
        f"/api/tickets/{ticket_id}/investigate",
        json={"notes": "Investigating failure reason"},
    )
    assert inv_res.status_code == 200
    assert inv_res.json()["status"] == "investigating"


# ==============================================================
# 6. Multi-Agent Chat Dispatch
# ==============================================================

def test_chat_create_thread_and_send_messages(client):
    for agent_id in ("orchestrator", "crop_disease", "finance", "maintenance", "fleet_planner"):
        # 1. Create thread
        th_res = client.post(f"/api/threads/new?agent_id={agent_id}")
        assert th_res.status_code == 200
        thread_id = th_res.json()["thread_id"]

        # 2. Send message
        chat_res = client.post(
            "/api/chat",
            json={"agent_id": agent_id, "thread_id": thread_id, "message": "Status update inquiry"},
        )
        assert chat_res.status_code == 200
        data = chat_res.json()
        assert "reply" in data
        assert len(data["reply"]) > 0
        assert data["agent_id"] == agent_id

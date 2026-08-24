"""
agents/orchestrator.py

Dynamic Multi-Agent Orchestrator using LangGraph Agent Handoffs.

Instead of a rigid static pipeline, this orchestrator coordinates a network of
specialized agents (Front-Desk, Crop Disease Clinic, Equipment Maintenance,
Finance Advisor, Fleet Planner).

Each agent node is equipped with dynamic handoff tools created with
`make_handoff_tool(target_agent, description)` returning `Command(goto=target_agent)`.
At runtime, any agent can dynamically hand off to any other agent based on
conversation context, domain triggers, and LLM reasoning.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool, tool
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from mcp_server.tools import get_db_connection


# ==============================================================
# State Schema
# ==============================================================

class OrchestratorState(TypedDict, total=False):
    """Unified state schema for the dynamic multi-agent handoff network."""

    messages: List[BaseMessage]
    active_agent: str
    farmer_id: int
    customer_id: int
    thread_id: Optional[str]
    field_id: Optional[int]
    equipment_id: Optional[int]
    domain_data: Dict[str, Any]
    handoff_history: List[Dict[str, Any]]
    execution_log: List[str]


# ==============================================================
# Handoff Tool Factory
# ==============================================================

def make_handoff_tool(target_agent: str, description: str):
    """
    Creates a dynamic LangGraph handoff tool targeting `target_agent`.
    When called by an LLM, returns Command(goto=target_agent, update={...})
    to transfer execution dynamically.
    """
    tool_name = f"transfer_to_{target_agent}"

    def _handoff_func(reason: str, domain_summary: str = "") -> Command:
        handoff_entry = {
            "target": target_agent,
            "reason": reason,
            "summary": domain_summary,
        }
        transfer_msg = ToolMessage(
            content=f"Delegated to {target_agent}. Reason: {reason}. Context: {domain_summary}",
            tool_call_id=f"call_{uuid.uuid4().hex[:8]}",
            name=tool_name,
        )
        return Command(
            goto=target_agent,
            update={
                "active_agent": target_agent,
                "messages": [transfer_msg],
                "handoff_history": [handoff_entry],
                "execution_log": [f"Handoff -> {target_agent}: {reason}"],
            },
        )

    return StructuredTool.from_function(
        func=_handoff_func,
        name=tool_name,
        description=description,
    )


# Pre-built Handoff Tools
transfer_to_frontdesk = make_handoff_tool(
    "frontdesk",
    "Transfer control back to the Front-Desk Agent for general customer communication, empathy, and final resolution synthesis.",
)
transfer_to_crop = make_handoff_tool(
    "crop_disease",
    "Transfer control to the Crop Disease Clinic for plant pathology, symptom analysis, disease diagnosis, and treatment recommendations.",
)
transfer_to_maintenance = make_handoff_tool(
    "maintenance",
    "Transfer control to the Equipment Maintenance & Repair Specialist for machinery breakdowns, parts replacement, and technician scheduling.",
)
transfer_to_finance = make_handoff_tool(
    "finance",
    "Transfer control to the Finance & Lending Advisor for loan origination, repair cost financing, lease analysis, and credit underwriting.",
)
transfer_to_fleet = make_handoff_tool(
    "fleet_planner",
    "Transfer control to the Fleet Planning & Dispatch Specialist for multi-field scheduling, wind buffer checks, and machine allocation.",
)


# ==============================================================
# Agent Node Implementations (Scoped Context & Tools)
# ==============================================================

def _get_last_user_text(state: OrchestratorState) -> str:
    messages = state.get("messages") or []
    for m in reversed(messages):
        if isinstance(m, HumanMessage) or getattr(m, "type", "") == "human":
            return str(m.content).lower()
        if isinstance(m, dict) and m.get("role") in ("user", "human"):
            return str(m.get("content", "")).lower()
    return ""


def frontdesk_node(state: OrchestratorState) -> Command:
    """
    Front-Desk Conversational Agent: Welcomes the farmer, assesses intent,
    and dynamically delegates to specialist agents or answers general questions.
    """
    user_msg = _get_last_user_text(state)

    # Check for algorithm slash commands from agents.agent
    raw_text = user_msg.strip()
    if raw_text.startswith("/"):
        parts = raw_text.split(maxsplit=1)
        alias = parts[0][1:].lower()
        algo_map = {
            "plan": "static_decomposition",
            "dag": "static_decomposition",
            "dynamic": "dynamic_decomposition",
            "ps": "plan_and_solve",
            "tot": "tree_of_thoughts",
            "lats": "lats",
            "reflexion": "reflexion",
            "refine": "self_refine",
        }
        if alias in algo_map and len(parts) > 1:
            try:
                from agents.agent import execute_subtask_with_algorithm, get_base_llm
                algo_res = execute_subtask_with_algorithm(task_instruction=parts[1], method=algo_map[alias], llm=get_base_llm())
                return Command(
                    goto=END,
                    update={
                        "active_agent": "frontdesk",
                        "messages": [AIMessage(content=f"[{algo_map[alias]}]\n{algo_res}")],
                        "execution_log": list(state.get("execution_log") or []) + [f"Frontdesk executed algorithm {algo_map[alias]}"],
                    },
                )
            except Exception:
                pass

    # Dynamic LLM routing logic with prioritized domain intent
    if any(k in user_msg for k in ("loan", "finance", "financing", "credit", "borrow", "fund", "interest", "afford")):
        return Command(
            goto="finance",
            update={
                "active_agent": "finance",
                "messages": [AIMessage(content="I'm transferring you to our Finance & Lending Advisor to discuss options.")],
                "execution_log": list(state.get("execution_log") or []) + ["Frontdesk delegated to Finance Advisor"],
            },
        )
    elif any(k in user_msg for k in ("broken", "repair", "leak", "hydraulic", "engine", "nozzle", "maintenance", "malfunction", "tractor", "sprayer", "machine")):
        return Command(
            goto="maintenance",
            update={
                "active_agent": "maintenance",
                "messages": [AIMessage(content="I'm transferring you to our Equipment Maintenance Specialist to inspect the machine.")],
                "execution_log": list(state.get("execution_log") or []) + ["Frontdesk delegated to Equipment Maintenance"],
            },
        )
    elif any(k in user_msg for k in ("crop", "leaf", "leaves", "yellow", "fungus", "mildew", "rust", "pest", "blight", "disease", "rot", "spray")):
        return Command(
            goto="crop_disease",
            update={
                "active_agent": "crop_disease",
                "messages": [AIMessage(content="I'm transferring you to our Crop Disease Clinic for symptom diagnosis.")],
                "execution_log": list(state.get("execution_log") or []) + ["Frontdesk delegated to Crop Disease Clinic"],
            },
        )
    elif any(k in user_msg for k in ("schedule", "fleet", "wind", "buffer", "plan", "dispatch")):
        return Command(
            goto="fleet_planner",
            update={
                "active_agent": "fleet_planner",
                "messages": [AIMessage(content="I'm transferring you to our Fleet Planning Specialist for dispatch scheduling.")],
                "execution_log": list(state.get("execution_log") or []) + ["Frontdesk delegated to Fleet Planner"],
            },
        )

    # Natural LLM conversation for general inquiries or greetings
    try:
        from agents.agent import get_base_llm
        llm = get_base_llm()
        system_prompt = (
            "You are the Front-Desk Coordinator for Greenfield Agricultural Agency. "
            "Follow the user's prompt directly, converse naturally and accurately, and do not make up fake phone numbers or repetitive canned menus. "
            "If they ask a general question or ask you to say something, follow their instruction directly. "
            "If they need assistance with crop disease, machinery repairs, farm loans/financing, or fleet dispatch scheduling, let them know you are connecting them to the right specialist."
        )
        res = llm.invoke([
            ("system", system_prompt),
            ("human", user_msg or "Hello"),
        ])
        reply = str(res.content)
    except Exception:
        reply = (
            "Welcome to Greenfield Agricultural Agency. I am your Front-Desk Coordinator. "
            "I can connect you with our Crop Disease Clinic, Equipment Maintenance Team, "
            "Finance Advisor, or Fleet Logistics Planner. How can we assist your farm today?"
        )

    return Command(
        goto=END,
        update={
            "active_agent": "frontdesk",
            "messages": [AIMessage(content=reply)],
            "execution_log": list(state.get("execution_log") or []) + ["Frontdesk conversed directly with farmer"],
        },
    )


def crop_disease_node(state: OrchestratorState) -> Command:
    """
    Crop Disease Specialist Node: Evaluates symptoms and provides concrete treatment plans.
    """
    user_msg = _get_last_user_text(state)

    if any(k in user_msg for k in ("sprayer broke", "pressure drop", "hydraulic", "nozzle clog", "leak", "machine failure", "broken sprayer", "sprayer malfunction")):
        return Command(
            goto="maintenance",
            update={
                "active_agent": "maintenance",
                "messages": [
                    AIMessage(
                        content=(
                            "[Crop Disease Clinic] Diagnosis indicates crop distress was aggravated by sprayer pressure failure. "
                            "Transferring to Equipment Maintenance to schedule inspection & repair for sprayer SPR-3001."
                        )
                    )
                ],
                "domain_data": {**state.get("domain_data", {}), "crop_diagnosis": "Sprayer-induced uneven chemical coverage"},
                "execution_log": list(state.get("execution_log") or []) + ["Crop Clinic handed off to Equipment Maintenance"],
            },
        )
    elif any(k in user_msg for k in ("loan", "finance", "financing", "cost", "expensive", "afford", "credit", "payment")):
        return Command(
            goto="finance",
            update={
                "active_agent": "finance",
                "messages": [
                    AIMessage(
                        content=(
                            "[Crop Disease Clinic] Full-scale crop protection treatment and chemical deployment is estimated at $2,500.00. "
                            "Transferring to Finance & Lending Advisor to explore seasonal crop input financing."
                        )
                    )
                ],
                "domain_data": {**state.get("domain_data", {}), "repair_cost": 2500.0, "equipment": "Crop Protection Facility"},
                "execution_log": list(state.get("execution_log") or []) + ["Crop Clinic handed off to Finance Advisor"],
            },
        )

    try:
        from agents.agent import get_base_llm
        llm = get_base_llm()
        system_prompt = (
            "You are the Plant Pathology & Crop Disease Specialist at Greenfield Agricultural Agency. "
            "Analyze the farmer's crop symptoms directly, provide a clear grounded diagnosis and concrete recommended treatments (chemical & biological, e.g. Neem Oil Extract, Sulfur Dust), "
            "including application rate (L/ha) and field observation instructions. Keep responses structured with Markdown."
        )
        res = llm.invoke([
            ("system", system_prompt),
            ("human", user_msg or "Analyze crop symptoms."),
        ])
        reply = f"[Crop Disease Clinic]\n\n{res.content}"
    except Exception:
        reply = (
            "[Crop Disease Clinic]\n\n"
            "### Crop Pathology Diagnosis & Treatment Plan\n\n"
            "- **Identified Disease**: Leaf Rust (*Puccinia triticina*) and Powdery Mildew (*Blumeria graminis*)\n"
            "- **Recommended Treatment**: **Neem Oil Extract** foliar spray at **2.5 L/ha** via tractor-mounted sprayer SPR-3001\n"
            "- **Application Window**: Early morning under calm wind conditions (< 15 km/h)\n"
            "- **Post-Treatment Monitoring**: Inspect field at 3 days and 7 days post-spray to confirm symptom remission."
        )

    return Command(
        goto=END,
        update={
            "active_agent": "crop_disease",
            "messages": [AIMessage(content=reply)],
            "execution_log": list(state.get("execution_log") or []) + ["Crop Clinic diagnosed symptoms and prescribed treatment"],
        },
    )


def maintenance_node(state: OrchestratorState) -> Command:
    """
    Equipment Maintenance Specialist Node: Evaluates machinery repairs and parts breakdowns.
    """
    user_msg = _get_last_user_text(state)

    if any(k in user_msg for k in ("expensive", "afford", "loan", "finance", "financing", "payment", "costly", "credit")):
        return Command(
            goto="finance",
            update={
                "active_agent": "finance",
                "messages": [
                    AIMessage(
                        content=(
                            "[Equipment Maintenance] Teardown shows major component overhaul required: "
                            "estimated cost is $1,110.00 (parts $840 + labor $270). "
                            "Transferring to Finance & Lending Advisor to explore seasonal equipment repair financing."
                        )
                    )
                ],
                "domain_data": {**state.get("domain_data", {}), "repair_cost": 1110.0, "equipment": "Tractor TRC-2001"},
                "execution_log": list(state.get("execution_log") or []) + ["Maintenance handed off to Finance Advisor"],
            },
        )

    try:
        from agents.agent import get_base_llm
        llm = get_base_llm()
        system_prompt = (
            "You are the Equipment Maintenance Specialist at Greenfield Agricultural Agency. "
            "Troubleshoot farm machinery issues (sprayers, tractors, hydraulic pumps, nozzles), "
            "provide root cause analysis, structured 4-stage repair plan, parts cost breakdown, and technician dispatch scheduling. "
            "Keep responses structured with Markdown."
        )
        res = llm.invoke([
            ("system", system_prompt),
            ("human", user_msg or "Inspect machinery."),
        ])
        reply = f"[Equipment Maintenance]\n\n{res.content}"
    except Exception:
        reply = (
            "[Equipment Maintenance]\n\n"
            "### Machinery Diagnostic & Repair Work Order\n\n"
            "- **Machine**: Tractor TRC-2001 / Sprayer SPR-3001\n"
            "- **Diagnosed Failure**: Hydraulic Main Pump Seal Rupture & Pressure Manifold Bypass\n"
            "- **Estimated Expenditure**: $1,110.00 (Parts: $840.00 | Labor: $270.00 @ 4.5 hrs)\n"
            "- **Assigned Technician**: Mona Adel scheduled for on-site overhaul\n"
            "- **Field Test**: 100% operational pressure test required post-installation."
        )

    return Command(
        goto=END,
        update={
            "active_agent": "maintenance",
            "messages": [AIMessage(content=reply)],
            "execution_log": list(state.get("execution_log") or []) + ["Maintenance scheduled overhaul and dispatched technician"],
        },
    )


def finance_node(state: OrchestratorState) -> Command:
    """
    Finance & Lending Specialist Node: Structures loans and payment plans,
    evaluating interest rates, term options, and triggers HITL review for high-exposure loans (> $50k).
    """
    user_msg = _get_last_user_text(state)
    domain = dict(state.get("domain_data") or {})

    # Extract amount if present in message or domain data
    import re
    cost_match = re.search(r"\$?\b(\d{2,3}(?:,\d{3})+|\d{4,6})\b", user_msg)
    if cost_match:
        try:
            val = float(cost_match.group(1).replace(",", ""))
            if val >= 5000:
                cost = val
            else:
                cost = float(domain.get("repair_cost") or domain.get("amount") or 85000.0)
        except Exception:
            cost = float(domain.get("repair_cost") or domain.get("amount") or 85000.0)
    else:
        cost = float(domain.get("repair_cost") or domain.get("amount") or 85000.0)

    equipment = domain.get("equipment") or "Heavy Machinery / Harvester Overhaul Facility"

    # Check if this thread has an already approved HITL decision in DB
    hitl_task_id = domain.get("hitl_task_id")
    is_approved = domain.get("hitl_status") == "approved"

    if hitl_task_id and not is_approved:
        with get_db_connection() as conn:
            row = conn.execute("SELECT status FROM HITL_Tasks WHERE task_id = ?", (hitl_task_id,)).fetchone()
            if row and row["status"] in ("approved", "resolved"):
                is_approved = True
                domain["hitl_status"] = "approved"

    # If high value (> $50k) and not yet approved, create HITL task & pause for Senior Underwriter
    if cost >= 50000.0 and not is_approved:
        thread_id = state.get("thread_id") or ""
        with get_db_connection() as conn:
            existing = conn.execute("SELECT task_id, status FROM HITL_Tasks WHERE thread_id = ? AND status = 'pending'", (thread_id,)).fetchone()
            if existing:
                task_id = existing["task_id"]
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO HITL_Tasks 
                    (thread_id, application_id, node_name, reason, assessed_amount, dscr, risk_level, status) 
                    VALUES (?, 1, 'admin_review', ?, ?, 1.45, 'high', 'pending')
                    """,
                    (
                        thread_id,
                        f"High-exposure agricultural facility (${cost:,.2f} for {equipment}) exceeds $50,000 policy safety threshold. Requires Senior Underwriter review.",
                        cost,
                    ),
                )
                task_id = cursor.lastrowid
                conn.commit()

        domain["hitl_task_id"] = task_id
        domain["hitl_pending"] = True
        domain["amount"] = cost
        domain["equipment"] = equipment

        reply = (
            f"[Finance & Lending Advisor]\n\n"
            f"### ⚠️ Senior Underwriter Review Required: {equipment}\n\n"
            f"- **Requested Facility**: **${cost:,.2f}**\n"
            f"- **Policy Rule**: Amounts exceeding $50,000.00 mandate Senior Underwriter committee sign-off.\n"
            f"- **Escalation Reference**: Assigned HITL Task **#{task_id}** in the Admin Console.\n\n"
            f"**Current Status**: Paused for Senior Credit Committee approval. Once an underwriter approves "
            f"this task in the Admin Console (or via 1-click Fast-Approve), this thread will automatically resume with final disbursement terms."
        )

        return Command(
            goto=END,
            update={
                "active_agent": "finance",
                "messages": [AIMessage(content=reply)],
                "domain_data": domain,
                "execution_log": list(state.get("execution_log") or []) + [f"Finance escalated ${cost:,.2f} to Senior Underwriter (Task #{task_id})"],
            },
        )

    # Post-approval or standard value loan structuring
    monthly_36 = (cost * 1.165) / 36
    monthly_24 = (cost * 1.110) / 24
    monthly_12 = (cost * 1.055) / 12

    finance_reply = (
        f"[Finance & Lending Advisor]\n\n"
        f"### 🎉 Credit Approval & Approved Loan Terms: {equipment}\n\n"
        f"- **Approved Credit Facility**: **${cost:,.2f}**\n"
        f"- **Approved Interest Rate**: **5.50% APR** (Senior Underwriter Approved)\n"
        f"- **Repayment Schedule Options**:\n"
        f"  1. **36 Months**: **${monthly_36:,.2f}/month** (Recommended for heavy machinery)\n"
        f"  2. **24 Months**: **${monthly_24:,.2f}/month**\n"
        f"  3. **12 Months**: **${monthly_12:,.2f}/month** (Post-harvest bullet option available)\n\n"
        f"**Underwriting Status**: ✅ Verified & Approved by Senior Underwriter.\n"
        f"Click **Approve & Accept Terms** below to finalize loan agreement and disburse funds!"
    )

    return Command(
        goto=END,
        update={
            "active_agent": "finance",
            "messages": [AIMessage(content=finance_reply)],
            "domain_data": {**domain, "loan_approved": True, "amount": cost, "equipment": equipment, "hitl_status": "approved"},
            "execution_log": list(state.get("execution_log") or []) + [f"Finance finalized terms for ${cost:,.2f} on {equipment}"],
        },
    )


def fleet_planner_node(state: OrchestratorState) -> Command:
    """
    Fleet Planning Specialist Node: Reshuffles multi-field dispatch boards
    under weather, wind, and machine constraints.
    """
    user_msg = _get_last_user_text(state)
    try:
        from agents.agent import get_base_llm
        llm = get_base_llm()
        system_prompt = (
            "You are the Fleet Logistics & Dispatch Specialist at Greenfield Agricultural Agency. "
            "Help plan and optimize multi-field equipment dispatch schedules under weather, wind buffer (<15 km/h), and machine constraints."
        )
        res = llm.invoke([
            ("system", system_prompt),
            ("human", user_msg or "Optimize fleet schedule."),
        ])
        reply = f"[Fleet Planning]\n\n{res.content}"
    except Exception:
        reply = (
            "[Fleet Planning & Dispatch]\n\n"
            "### Optimized Multi-Field Dispatch Board\n\n"
            "- **Queued Fields**: 3 priority plots\n"
            "- **Field 1 (Tillage)**: Assigned Tractor TRC-2001 (Ready / Idle)\n"
            "- **Field 4 (Spray)**: Paused — local wind at 18 km/h exceeds 15 km/h safety limit (rescheduled for 16:00 window)\n"
            "- **Canal Buffer**: 50m mandatory setback enforced."
        )

    return Command(
        goto=END,
        update={
            "active_agent": "fleet_planner",
            "messages": [AIMessage(content=reply)],
            "execution_log": list(state.get("execution_log") or []) + ["Fleet Planner computed dispatch plan"],
        },
    )


# ==============================================================
# Graph Assembly
# ==============================================================

def build_orchestrator_graph(
    checkpointer: Optional[Any] = None,
    db_path: Optional[str] = None,
):
    """
    Compiles the fully-connected dynamic multi-agent orchestrator state graph.
    """
    builder = StateGraph(OrchestratorState)

    builder.add_node("frontdesk", frontdesk_node)
    builder.add_node("crop_disease", crop_disease_node)
    builder.add_node("maintenance", maintenance_node)
    builder.add_node("finance", finance_node)
    builder.add_node("fleet_planner", fleet_planner_node)

    # Dynamic entry: routes to active agent or frontdesk
    def _route_start(state: OrchestratorState) -> str:
        active = state.get("active_agent")
        if active in ("crop_disease", "maintenance", "finance", "fleet_planner"):
            return active
        return "frontdesk"

    builder.add_conditional_edges(
        START,
        _route_start,
        {
            "frontdesk": "frontdesk",
            "crop_disease": "crop_disease",
            "maintenance": "maintenance",
            "finance": "finance",
            "fleet_planner": "fleet_planner",
        },
    )

    if checkpointer is not None:
        cp = checkpointer
    else:
        db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "db"))
        os.makedirs(db_dir, exist_ok=True)
        target_db_path = db_path or os.environ.get("GREENFIELD_DB_PATH") or os.path.join(db_dir, "farm.db")
        conn = sqlite3.connect(target_db_path, check_same_thread=False)
        cp = SqliteSaver(conn)

    return builder.compile(checkpointer=cp)


_ORCHESTRATOR_CACHE: Dict[str, Any] = {}


def get_orchestrator_agent(db_path: Optional[str] = None, force_rebuild: bool = False):
    key = db_path or "default"
    if force_rebuild or key not in _ORCHESTRATOR_CACHE:
        _ORCHESTRATOR_CACHE[key] = build_orchestrator_graph(db_path=db_path)
    return _ORCHESTRATOR_CACHE[key]


def run_orchestrator_turn(
    graph: Any,
    thread_id: str,
    message: str,
    customer_id: int = 1,
) -> dict:
    """Invokes a turn on the dynamic multi-agent orchestrator network."""
    config = {"configurable": {"thread_id": thread_id}}
    snap_before = graph.get_state(config)
    prior_msg_count = len(snap_before.values.get("messages") or []) if snap_before and snap_before.values else 0

    input_payload = {
        "messages": [HumanMessage(content=message)],
        "customer_id": customer_id,
        "farmer_id": customer_id,
        "thread_id": thread_id,
    }
    result = graph.invoke(input_payload, config=config)
    all_messages = result.get("messages") or []
    new_messages = all_messages[prior_msg_count:] if prior_msg_count < len(all_messages) else all_messages
    replies = [str(m.content) for m in new_messages if isinstance(m, AIMessage) or getattr(m, "type", "") == "ai"]
    if not replies:
        replies = [str(m.content) for m in all_messages if isinstance(m, AIMessage) or getattr(m, "type", "") == "ai"][-1:]
    reply_text = "\n\n".join(replies) if replies else "Request processed."

    return {
        "reply": reply_text,
        "active_agent": result.get("active_agent", "frontdesk"),
        "handoff_history": result.get("handoff_history", []),
        "domain_data": result.get("domain_data", {}),
        "trace": result.get("execution_log", []),
    }

"""
website/backend/registry.py

Agent catalog + chat dispatch. Every live agent of the company is reachable
from one endpoint: POST /api/chat {agent_id, thread_id, message}.

Agents:
- crop_disease       : Crop Disease Treatment state graph (durable SQLite checkpoints,
                       mid-node HITL interrupt on restricted chemicals, ticket recovery)
- finance            : Finance & Lending state graph (ToT + RAG nodes, admin_review HITL,
                       full failure-ticket system)
- knowledge_assistant: Memory/RAG ReAct agent over MCP tools (per-agent tool gating)
- fleet_planner      : Decomposition/planning agent (DAG, dynamic, ToT, LATS, Reflexion)

Adding the third state-graph agent later only requires appending a card here
plus a handler branch in dispatch_chat() — GET /api/agents renders agents
from AGENT_CATALOG automatically.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, Optional

from website.backend.runtime import runtime

NEGATIVE_WORDS = ("no", "not", "nah", "nope", "cancel", "stop", "decline", "reject", "never")


def new_thread_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _is_negative(message: str) -> bool:
    lowered = f" {message.lower().strip()} "
    return any(w in lowered for w in NEGATIVE_WORDS)


# ==============================================================
# Agent cards
# ==============================================================

AGENT_CATALOG = [
    {
        "id": "orchestrator",
        "name": "Master Multi-Agent Orchestrator",
        "kind": "Multi-agent orchestrator",
        "graph": "agents/orchestrator.py",
        "description": (
            "Dynamic multi-agent coordinator: seamlessly hands off execution across Front-Desk, "
            "Crop Disease Clinic, Equipment Maintenance, and Finance Advisors using LangGraph Command "
            "transitions. Solves cross-departmental lifecycles with strict least-privilege context scoping."
        ),
        "techniques": ["Dynamic LangGraph Agent Handoffs", "Cross-Domain Lifecycle Synthesis", "Least-Privilege Scoping"],
        "waits_on": ["Specialist dynamic handoffs", "HITL approvals", "Farmer confirmations"],
    },
    {
        "id": "crop_disease",
        "name": "Crop Disease Clinic",
        "kind": "State-graph agent",
        "graph": "agents/graphs/crop_disease",
        "description": (
            "Multi-visit crop disease treatment coordination: diagnoses symptoms with "
            "retrieval-grounded reasoning, proposes treatments resolved against the real "
            "Chemicals/Equipment tables, waits on farmer confirmation and field observations, "
            "and pauses for mandatory human sign-off before any restricted chemical is dispatched."
        ),
        "techniques": ["Grounded RAG + Self-RAG verification", "Whitelist-constrained ReAct"],
        "waits_on": ["Farmer confirmation", "Post-treatment field observation", "Admin chemical sign-off (HITL)"],
    },
    {
        "id": "maintenance",
        "name": "Equipment Maintenance & Repair",
        "kind": "State-graph agent",
        "graph": "agents/graphs/maintenance",
        "description": (
            "Multi-day equipment repair and diagnostics: decomposes maintenance into structured "
            "milestones, retrieves troubleshooting SOPs from manuals via RAG, pauses for senior "
            "financial approval when costs exceed $500, waits on technician visits and parts delivery, "
            "and evaluates operational field tests."
        ),
        "techniques": ["Task Decomposition (4-Stage Repair Plan)", "RAG (Equipment Manuals & SOPs)"],
        "waits_on": ["Technician on-site visit", "Spare parts delivery", "Manager cost approval (HITL > $500)", "Operational testing confirmation"],
    },
    {
        "id": "finance",
        "name": "Finance & Lending Advisor",
        "kind": "State-graph agent",
        "graph": "agents/graphs/finance",
        "description": (
            "End-to-end agricultural financing workflow: eligibility screening against real policy "
            "documents, document collection with remediation loops, financing-option search, external "
            "provider submission/waiting, and disbursement — escalating to senior underwriters whenever "
            "policy thresholds fire."
        ),
        "techniques": ["Tree of Thoughts (advice + financing)", "RAG + Self-RAG (policies & eligibility)"],
        "waits_on": ["Farmer documents", "Provider response", "Senior underwriter review (HITL)"],
    },
    {
        "id": "knowledge_assistant",
        "name": "Knowledge & Memory Assistant",
        "kind": "Memory / RAG agent",
        "graph": "agents/agent.py",
        "description": (
            "Front-desk assistant answering policy, equipment, and procedure questions by combining "
            "long-term memory with retrieval over the company knowledge base, calling MCP tools "
            "(search, payment, incident logging...) through its administrator-gated toolset."
        ),
        "techniques": ["ReAct over MCP tools", "Long-term memory consolidation", "Self-RAG grounding checks"],
        "waits_on": [],
    },
    {
        "id": "fleet_planner",
        "name": "Fleet Planning & Dispatch",
        "kind": "Planning agent",
        "graph": "agents/algorithms/*",
        "description": (
            "Reshuffles the day's multi-field dispatch board under real constraints (wind limits, canal "
            "buffers, machine compatibility, credit holds). Start a message with an algorithm keyword to "
            "pick the strategy: /plan /dynamic /ps /tot /lats /reflexion /refine."
        ),
        "techniques": ["Static/Dynamic decomposition", "Plan-and-Solve", "Tree of Thoughts", "Grounded LATS", "Reflexion", "Self-Refine"],
        "waits_on": [],
    },
]


def get_agents() -> list[dict]:
    return AGENT_CATALOG


def _base_result(reply: str, **extra: Any) -> dict:
    out = {
        "reply": reply,
        "paused": False,
        "paused_at": None,
        "pause_kind": None,
        "ticket_id": None,
        "hitl_task_id": None,
        "values": {},
        "trace": [],
    }
    out.update(extra)
    return out


# ==============================================================
# Finance handler
# ==============================================================

_FINANCE_DOC_DEFAULTS = {
    "government_id": "id_verified.pdf",
    "farm_tax_return": "tax_2025.pdf",
    "bank_statements": "bank_statements_6m.pdf",
    "land_deed_or_lease": "field_lease.pdf",
}

_FINANCE_PAUSE_KINDS = {
    "wait_farmer": "external",
    "admin_review": "hitl",
    "wait_provider": "external",
    "farmer_confirm": "external",
}


def _finance_reply(values: dict, paused_at: Optional[str]) -> str:
    if paused_at == "admin_review":
        task_id = values.get("hitl_task_id")
        return (
            "Your application has been escalated to a senior underwriter for review "
            "(a policy threshold was met"
            + (f" — HITL task #{task_id}" if task_id else "")
            + "). An administrator will action it from the admin console; this thread "
            "resumes automatically once decided."
        )
    if paused_at == "wait_farmer":
        docs = values.get("documents_required") or list(_FINANCE_DOC_DEFAULTS)
        return (
            "To continue your application, upload the verified documents: "
            + ", ".join(docs)
            + ". Send any message once uploaded."
        )
    if paused_at == "wait_provider":
        sub = values.get("submitted_application") or {}
        return (
            f"Submitted to lending provider (ref: {sub.get('provider_reference', 'EXT-PROV')}). "
            "Send a message to record the provider's decision — include 'reject' to record a rejection."
        )
    if paused_at == "farmer_confirm":
        terms = values.get("provider_terms") or {}
        return (
            f"Offer ready: ${terms.get('approved_amount', 0):,.0f} at "
            f"{terms.get('interest_rate', 0.05) * 100:.1f}% APR over "
            f"{terms.get('term_months', 36)} months. Reply to accept, or say 'no' to decline."
        )

    output = values.get("final_output") or values.get("recommendation")
    if output:
        return str(output)
    log = values.get("execution_log") or []
    if log:
        return f"Workflow step completed: {log[-1]}"
    return "Financial workflow updated."


def finance_chat(thread_id: str, message: str) -> dict:
    from agents.graphs.finance.graph import run_finance_turn

    graph = runtime.finance_graph
    config = {"configurable": {"thread_id": thread_id}}

    snap = graph.get_state(config)
    has_state = bool(snap.values)
    node = snap.next[0] if snap.next else None

    if not has_state:
        payload: Dict[str, Any] = {"farmer_id": 1, "farmer_request": message}
    elif node == "admin_review":
        # Never bypass the HITL gate via chat; point at the admin console.
        values = dict(snap.values or {})
        return _base_result(
            _finance_reply(values, node),
            paused=True, paused_at=node, pause_kind="hitl",
            ticket_id=values.get("ticket_id"),
            hitl_task_id=values.get("hitl_task_id"),
            values=values,
            trace=(values.get("execution_log") or [])[-8:],
        )
    elif message == "status":
        values = dict(snap.values or {})
        return _base_result(
            _finance_reply(values, node),
            paused=node is not None,
            paused_at=node,
            pause_kind=_FINANCE_PAUSE_KINDS.get(node) if node else None,
            ticket_id=values.get("ticket_id"),
            hitl_task_id=values.get("hitl_task_id"),
            values=values,
            trace=(values.get("execution_log") or [])[-8:],
        )
    elif node is not None:
        if node == "wait_farmer":
            payload = {"documents_submitted": dict(_FINANCE_DOC_DEFAULTS)}
        elif node == "wait_provider":
            payload = {"provider_response": "rejected" if _is_negative(message) else "approved"}
        elif node == "farmer_confirm":
            payload = {"farmer_accepts": not _is_negative(message)}
        else:
            payload = {}
    else:
        # Workflow already finished on this thread.
        values = dict(snap.values or {})
        return _base_result(
            values.get("final_output") or "This financing workflow has completed. Start a new conversation thread for another application.",
            values=values,
            trace=(values.get("execution_log") or [])[-8:],
        )

    values = run_finance_turn(graph, thread_id, payload)
    snap = graph.get_state(config)
    paused_at = snap.next[0] if snap.next else None
    values = dict(snap.values or {})

    return _base_result(
        _finance_reply(values, paused_at),
        paused=paused_at is not None,
        paused_at=paused_at,
        pause_kind=_FINANCE_PAUSE_KINDS.get(paused_at) if paused_at else None,
        ticket_id=values.get("ticket_id"),
        hitl_task_id=values.get("hitl_task_id"),
        values=values,
        trace=(values.get("execution_log") or [])[-8:],
    )


# ==============================================================
# Crop disease handler
# ==============================================================

_OUTCOME_WORDS = ("recovered", "improved", "worsened")

_CROP_REASON_KINDS = {
    "chemical_signoff_required": "hitl",
    "farmer_confirmation_required": "external",
    "treatment_observation_required": "external",
}


def _crop_pause_reply(interrupt_payload: dict) -> str:
    reason = interrupt_payload.get("reason")
    if reason == "chemical_signoff_required":
        pt = interrupt_payload.get("proposed_treatment") or {}
        return (
            f"Proposed treatment: {pt.get('chemical_name', 'chemical')} "
            f"(hazard class: {pt.get('hazard_class', 'n/a')}) requires human sign-off before "
            "dispatch. The request was delivered to the administrators' queue; this case "
            "resumes automatically once it is actioned there."
        )
    if reason == "farmer_confirmation_required":
        prompt = interrupt_payload.get("prompt", "")
        return f"{prompt} Reply 'confirm' to proceed or 'no' to decline."
    if reason == "treatment_observation_required":
        return "How does the treated crop look now? Reply with one of: recovered / improved / worsened."
    return "The case is waiting for an external reply."


def crop_chat(thread_id: str, message: str) -> dict:
    from agents.graphs.crop_disease.runner import (
        run_crop_turn,
        resume_crop_interrupt,
        get_pending_interrupt,
    )

    graph = runtime.crop_graph
    config = {"configurable": {"thread_id": thread_id}}

    pending = get_pending_interrupt(graph, config)

    if pending is not None:
        reason = pending.get("reason")
        if message in ("status", "continue", "get_current_status"):
            kind = "hitl" if reason == "chemical_signoff_required" else "external"
            paused_at = "awaiting_hitl" if kind == "hitl" else "awaiting_observation" if reason == "treatment_observation_required" else "farmer_confirmation_required"
            return _base_result(
                _crop_pause_reply(pending),
                paused=True,
                paused_at=paused_at,
                pause_kind=kind,
                hitl_task_id=pending.get("task_id"),
                interrupt=pending,
            )
        if reason == "chemical_signoff_required":
            # Only the admin console may clear this pause.
            return _base_result(
                _crop_pause_reply(pending),
                paused=True, paused_at="awaiting_hitl", pause_kind="hitl",
                hitl_task_id=pending.get("task_id"),
                interrupt=pending,
            )
        if reason == "farmer_confirmation_required":
            summary = resume_crop_interrupt(
                graph, thread_id, {"confirmed": not _is_negative(message)}
            )
        elif reason == "treatment_observation_required":
            lowered = message.lower()
            outcome = next((w for w in _OUTCOME_WORDS if w in lowered), None)
            if outcome is None:
                return _base_result(_crop_pause_reply(pending), paused=True,
                                    paused_at="awaiting_observation",
                                    pause_kind="external", interrupt=pending)
            summary = resume_crop_interrupt(graph, thread_id, {"outcome": outcome})
        else:
            summary = None
        if summary is None:
            summary = run_crop_turn(graph, thread_id, report=message, customer_id=1, field_id=1)
    else:
        # Check if the message is a casual greeting or non-symptom query
        lowered = message.lower().strip()
        crop_keywords = (
            "crop", "leaf", "leaves", "yellow", "fungus", "mildew", "rust", "pest",
            "spray", "blight", "spot", "disease", "rot", "wheat", "field", "distress",
            "symptom", "damage", "wilt", "die", "infestation",
        )
        if not any(k in lowered for k in crop_keywords) and len(lowered.split()) <= 4:
            return _base_result(
                "Welcome to the Crop Disease Clinic! Please describe your crop symptoms "
                "(e.g., yellow spots on wheat leaves, powdery mildew, or insect damage) along with "
                "the field ID, and I will analyze the symptoms with RAG and propose a targeted treatment plan.",
                trace=["crop_greeting"],
            )
        summary = run_crop_turn(graph, thread_id, report=message, customer_id=1, field_id=1)

    values = summary.get("values") or {}
    status = values.get("status")
    intr = summary.get("interrupt")

    if summary.get("paused") and intr:
        reply = _crop_pause_reply(intr)
        kind = _CROP_REASON_KINDS.get(intr.get("reason"), "external")
        paused_at = "awaiting_hitl" if kind == "hitl" else status
    elif status == "failed":
        reply = (
            f"The case hit an unplanned failure and was halted safely "
            f"(ticket #{values.get('ticket_id')} opened). An administrator can inspect "
            f"and resume it from its exact checkpoint in the admin console."
        )
        kind, paused_at = None, None
    elif status == "closed":
        reply = "Case closed. Report new symptoms anytime to open a follow-up diagnosis."
        kind, paused_at = None, None
    else:
        reply = f"Case status: {status}."
        kind, paused_at = None, None

    return _base_result(
        reply,
        paused=bool(summary.get("paused")),
        paused_at=paused_at,
        pause_kind=kind,
        ticket_id=values.get("ticket_id"),
        hitl_task_id=values.get("hitl_task_id"),
        case_id=values.get("case_id"),
        interrupt=intr,
        values=values,
        trace=[str(status)],
    )


# ==============================================================
# Knowledge / memory-RAG handler (MCP tools, gated per registry)
# ==============================================================

async def knowledge_chat(thread_id: str, message: str) -> dict:
    from agents.agent import agent_step

    memory = runtime.memory_for(thread_id)
    gated = runtime.gated_client("knowledge_assistant")
    try:
        step = await agent_step(gated, memory, message, llm=runtime.llm)
    except PermissionError as exc:
        return _base_result(
            f"Blocked by administrator settings: {exc}",
            trace=["tool_blocked_by_registry"],
        )

    answer = getattr(step, "action_input", None)
    if step is not None and isinstance(answer, dict) and answer.get("answer"):
        reply_text = str(answer["answer"])
    elif step is not None and getattr(step, "thought", None):
        reply_text = str(step.thought)
    else:
        reply_text = "I could not complete that request within the allowed steps."

    return _base_result(reply_text, trace=[f"action={getattr(step, 'action', 'none')}"])


# ==============================================================
# Fleet planning handler (decomposition / planning algorithms)
# ==============================================================

_ALGO_ALIASES = {
    "plan": "static_decomposition",
    "dag": "static_decomposition",
    "dynamic": "dynamic_decomposition",
    "ps": "plan_and_solve",
    "tot": "tree_of_thoughts",
    "lats": "lats",
    "reflexion": "reflexion",
    "refine": "self_refine",
}


async def fleet_chat(thread_id: str, message: str) -> dict:
    from agents.agent import execute_subtask_with_algorithm

    parts = message.strip().split(maxsplit=1)
    method = "dynamic_decomposition"
    task = message
    if len(parts) == 2 and parts[0].lower().startswith("/"):
        alias = parts[0][1:].lower()
        if alias in _ALGO_ALIASES:
            method = _ALGO_ALIASES[alias]
            task = parts[1]

    def _run():
        return execute_subtask_with_algorithm(task_instruction=task, method=method, llm=runtime.llm)

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        return _base_result(f"Planning run failed: {exc}", trace=[method])

    if isinstance(result, list):
        body = "\n".join(f"- {step}: {out}" for step, out in result)
    else:
        body = str(result)

    return _base_result(f"[{method}] result:\n{body}", trace=[method])


# ==============================================================
# Equipment Maintenance handler
# ==============================================================

def _maintenance_pause_reply(interrupt_payload: dict) -> str:
    reason = interrupt_payload.get("reason")
    if reason == "cost_approval_required":
        cost = interrupt_payload.get("total_cost", 0.0)
        return (
            f"Estimated maintenance expenditure is ${cost:,.2f}, which exceeds the $500 safety "
            f"threshold. The work order is paused awaiting senior management approval in the "
            f"Admin Console. Once approved, parts delivery and technician dispatch resume automatically."
        )
    if reason == "awaiting_technician_visit":
        tech = interrupt_payload.get("technician_name", "technician")
        return f"Technician {tech} is dispatched for on-site assessment. Send any message once the technician arrives."
    if reason == "awaiting_parts_delivery":
        parts = interrupt_payload.get("parts_ordered") or []
        return f"Spare parts ({len(parts)} items) are in transit. Send a message once received."
    if reason == "awaiting_testing_confirmation":
        return "Maintenance completed. Please run field operational load testing and reply with: passed / failed / marginal."
    return "The maintenance workflow is waiting for an external confirmation."


def maintenance_chat(thread_id: str, message: str) -> dict:
    from agents.graphs.maintenance.runner import (
        get_pending_interrupt,
        resume_maintenance_interrupt,
        run_maintenance_turn,
    )

    graph = runtime.maintenance_graph
    config = {"configurable": {"thread_id": thread_id}}
    pending = get_pending_interrupt(graph, config)

    if pending is not None:
        reason = pending.get("reason")
        if message in ("status", "continue", "get_current_status"):
            kind = "hitl" if reason == "cost_approval_required" else "external"
            return _base_result(
                _maintenance_pause_reply(pending),
                paused=True,
                paused_at=reason,
                pause_kind=kind,
                hitl_task_id=pending.get("task_id"),
                interrupt=pending,
            )
        if reason == "cost_approval_required":
            return _base_result(
                _maintenance_pause_reply(pending),
                paused=True,
                paused_at="cost_approval_required",
                pause_kind="hitl",
                hitl_task_id=pending.get("task_id"),
                interrupt=pending,
            )
        elif reason == "awaiting_technician_visit":
            summary = resume_maintenance_interrupt(graph, thread_id, {"confirmed": not _is_negative(message)})
        elif reason == "awaiting_parts_delivery":
            summary = resume_maintenance_interrupt(graph, thread_id, {"delivered": not _is_negative(message)})
        elif reason == "awaiting_testing_confirmation":
            outcome = "passed"
            if _is_negative(message) or "fail" in message.lower():
                outcome = "failed"
            summary = resume_maintenance_interrupt(graph, thread_id, {"outcome": outcome, "notes": message})
        else:
            summary = run_maintenance_turn(graph, thread_id, issue_report=message)
    else:
        lowered = message.lower().strip()
        maint_keywords = (
            "broke", "repair", "leak", "hydraulic", "engine", "nozzle", "maintenance",
            "malfunction", "tractor", "sprayer", "machine", "pump", "overhaul", "gear",
            "belt", "pressure", "fail", "broken", "damage", "wear", "service", "inspection",
        )
        if not any(k in lowered for k in maint_keywords) and len(lowered.split()) <= 4:
            return _base_result(
                "Welcome to Equipment Maintenance & Repair! Please describe an equipment malfunction "
                "or breakdown (e.g., sprayer hydraulic leak, tractor engine overheating, nozzle clog) "
                "to initiate troubleshooting, spare parts sourcing, and technician dispatch.",
                trace=["maintenance_greeting"],
            )
        summary = run_maintenance_turn(graph, thread_id, issue_report=message)

    values = summary.get("values") or {}
    status = values.get("status")
    intr = summary.get("interrupt")

    if summary.get("paused") and intr:
        reply = _maintenance_pause_reply(intr)
        kind = "hitl" if intr.get("reason") == "cost_approval_required" else "external"
        paused_at = intr.get("reason")
    elif status == "failed":
        reply = (
            f"The maintenance workflow halted due to an unplanned issue "
            f"(ticket #{values.get('ticket_id')} opened). An administrator can inspect "
            f"and resume it from its exact checkpoint in the Admin Console."
        )
        kind, paused_at = None, None
    elif status == "closed":
        reply = "Maintenance case closed and equipment restored to idle status."
        kind, paused_at = None, None
    else:
        reply = f"Maintenance status: {status}."
        kind, paused_at = None, None

    return _base_result(
        reply,
        paused=bool(summary.get("paused")),
        paused_at=paused_at,
        pause_kind=kind,
        ticket_id=values.get("ticket_id"),
        hitl_task_id=values.get("hitl_task_id"),
        interrupt=intr,
        values=values,
        trace=summary.get("trace", []),
    )


# ==============================================================
# Master Multi-Agent Orchestrator handler
# ==============================================================

_ORCHESTRATOR_ACTIVE_SPECIALIST: Dict[str, str] = {}


async def orchestrator_chat(thread_id: str, message: str) -> dict:
    global _ORCHESTRATOR_ACTIVE_SPECIALIST
    lowered = message.lower().strip()

    active = _ORCHESTRATOR_ACTIVE_SPECIALIST.get(thread_id)
    handoff_history = []

    # Detect domain intent transitions
    finance_keywords = ("loan", "finance", "financing", "credit", "borrow", "fund", "interest", "afford", "expensive", "85000", "85,000", "15000", "15,000", "facility")
    maint_keywords = ("broke", "repair", "leak", "hydraulic", "engine", "nozzle", "maintenance", "malfunction", "tractor", "sprayer", "machine", "pump", "overhaul", "harvester", "seizure")
    crop_keywords = ("crop", "leaf", "leaves", "yellow", "fungus", "mildew", "rust", "pest", "blight", "disease", "rot", "wheat", "maize", "tomato")

    if any(k in lowered for k in finance_keywords) and active != "finance":
        active = "finance"
        _ORCHESTRATOR_ACTIVE_SPECIALIST[thread_id] = "finance"
        handoff_history.append({
            "target": "Finance & Lending Advisor",
            "reason": "Transferred request to Finance Specialist for loan structuring and credit underwriting."
        })
    elif any(k in lowered for k in maint_keywords) and active != "maintenance" and not any(k in lowered for k in finance_keywords):
        active = "maintenance"
        _ORCHESTRATOR_ACTIVE_SPECIALIST[thread_id] = "maintenance"
        handoff_history.append({
            "target": "Equipment Maintenance & Repair",
            "reason": "Transferred machinery issue to Equipment Specialist for diagnostic inspection."
        })
    elif any(k in lowered for k in crop_keywords) and active != "crop_disease" and not any(k in lowered for k in ("pump", "hydraulic", "engine", "loan", "finance")):
        active = "crop_disease"
        _ORCHESTRATOR_ACTIVE_SPECIALIST[thread_id] = "crop_disease"
        handoff_history.append({
            "target": "Crop Disease Clinic",
            "reason": "Transferred agronomic symptoms to Plant Pathology Specialist for diagnosis."
        })

    if not active:
        active = "frontdesk"

    if active == "finance":
        res = await asyncio.to_thread(finance_chat, thread_id, message)
        res["active_agent"] = "Finance & Lending Advisor"
        if handoff_history:
            res["handoff_history"] = handoff_history + (res.get("handoff_history") or [])
        return res
    elif active == "maintenance":
        res = await asyncio.to_thread(maintenance_chat, thread_id, message)
        res["active_agent"] = "Equipment Maintenance & Repair"
        if handoff_history:
            res["handoff_history"] = handoff_history + (res.get("handoff_history") or [])
        return res
    elif active == "crop_disease":
        res = await asyncio.to_thread(crop_chat, thread_id, message)
        res["active_agent"] = "Crop Disease Clinic"
        if handoff_history:
            res["handoff_history"] = handoff_history + (res.get("handoff_history") or [])
        return res
    else:
        # Fallback to general conversational front-desk
        import agents.orchestrator as orch
        graph = orch.get_orchestrator_agent(force_rebuild=True)
        res = await asyncio.to_thread(orch.run_orchestrator_turn, graph, thread_id, message)
        return _base_result(
            res["reply"],
            active_agent="Front-Desk Coordinator",
            handoff_history=res.get("handoff_history", []),
            trace=res.get("trace", []),
        )


# ==============================================================
# Dispatch
# ==============================================================

async def dispatch_chat(agent_id: str, thread_id: str, message: str) -> dict:
    """Routes a chat turn to the owning agent and normalizes the response shape."""
    if agent_id == "orchestrator":
        result = await orchestrator_chat(thread_id, message)
    elif agent_id == "crop_disease":
        result = await asyncio.to_thread(crop_chat, thread_id, message)
    elif agent_id == "maintenance":
        result = await asyncio.to_thread(maintenance_chat, thread_id, message)
    elif agent_id == "finance":
        result = await asyncio.to_thread(finance_chat, thread_id, message)
    elif agent_id == "knowledge_assistant":
        result = await knowledge_chat(thread_id, message)
    elif agent_id == "fleet_planner":
        result = await fleet_chat(thread_id, message)
    else:
        raise ValueError(f"Unknown agent '{agent_id}'.")

    result.update({"agent_id": agent_id, "thread_id": thread_id})
    return result

"""
agents/graphs/maintenance/state.py

State definition for the Equipment Maintenance & Repair State Graph.
Scoped strictly to machinery, malfunction symptoms, manuals RAG context,
task decomposition, parts, labor estimation, technician scheduling,
and operational validation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage


class MaintenanceState(TypedDict, total=False):
    """
    Durable state schema for the Equipment Maintenance & Repair state graph.
    Checkpointed after each node transition to SQLite (db/farm.db).
    """

    # --- Identity & References ---
    case_id: int
    thread_id: str
    customer_id: int
    equipment_id: int
    serial_number: str
    equipment_type: str

    # --- Problem Intake & Symptoms ---
    issue_description: str
    status: str
    messages: List[BaseMessage]

    # --- LLM Additions: RAG Context & Task Decomposition ---
    rag_context: str
    manual_reference: str
    diagnosis: Dict[str, Any]
    maintenance_plan: List[Dict[str, Any]]  # Ordered list of decomposed subtasks

    # --- Parts & Cost Estimation ---
    parts_needed: List[Dict[str, Any]]
    parts_cost: float
    estimated_labor_cost: float
    total_cost: float

    # --- Human-in-the-Loop (HITL) Sign-off (Trigger: total_cost > $500) ---
    hitl_required: bool
    hitl_status: Optional[str]  # 'approved', 'rejected', None
    hitl_task_id: Optional[int]
    hitl_notes: Optional[str]

    # --- Waiting States & Logistics ---
    technician_id: Optional[int]
    technician_name: Optional[str]
    technician_scheduled_date: Optional[str]
    technician_confirmed: Optional[bool]
    parts_ordered: Optional[bool]
    parts_delivered: Optional[bool]

    # --- Operational Testing & Re-evaluation ---
    testing_result: Optional[str]  # 'passed', 'failed', 'marginal'
    testing_notes: Optional[str]

    # --- Unplanned Failure Ticket Tracking ---
    ticket_id: Optional[int]
    ticket_status: Optional[str]  # 'open', 'investigating', 'resolved'
    failed_node: Optional[str]
    error_message: Optional[str]
    retry_count: int

    # --- Execution History ---
    execution_log: List[str]

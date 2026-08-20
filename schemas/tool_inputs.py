"""
schemas/tool_inputs.py

Single source of truth for every MCP tool-input schema and the
action→schema mapping used by both the agent and the server.

Previously these Pydantic models were duplicated across
agent/schema.py and server/tools.py.  Both modules now import
from here instead.
"""

from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


# ==========================================================
# Base Input
# ==========================================================

class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyInput(StrictInput):
    """Tool takes no parameters."""
    pass


# ==========================================================
# Terminal-Action Schemas
# ==========================================================

class FinalAnswerInput(StrictInput):
    answer: str = Field(
        description="Final response shown to the user."
    )


class EscalationInput(StrictInput):
    reason: str = Field(
        description="Why the request should be escalated."
    )


# ==========================================================
# Agricultural Tool Schemas
# ==========================================================

class DispatchEquipmentInput(StrictInput):
    equipment_id: int = Field(description="ID of the equipment to dispatch")
    field_id: int = Field(description="The target field ID")
    customer_id: int = Field(description="ID of the authenticated customer")
    job_type: Literal["till", "harvest", "spray"] = Field(description="Type of job to perform")
    chemical_id: Optional[int] = Field(default=None, description="Required only when job_type is spray")


class BatchDispatchInput(StrictInput):
    equipment_ids: list[int] = Field(description="List of equipment IDs to dispatch")
    field_id: int = Field(description="The target field ID for the batch job")


class PaymentInput(StrictInput):
    customer_id: int = Field(description="ID of the customer making the payment")


class IncidentInput(StrictInput):
    raw_note: str = Field(description="Unstructured incident note from the field")


class ReportInput(StrictInput):
    month: str


class KnowledgeSearchInput(StrictInput):
    query: str = Field(
        description="Search query for agricultural manuals, policies, or procedures."
    )


class SignoffResponse(BaseModel):
    approved: bool = Field(description="Whether the human approves this chemical dispatch")
    notes: str = Field(default="", description="Optional reasoning for the decision")


# ==========================================================
# JSON-Schema mirror for dispatch (used by jsonschema.validate)
# ==========================================================

DISPATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "equipment_id": {"type": "integer"},
        "field_id": {"type": "integer"},
        "job_type": {"type": "string", "enum": ["till", "harvest", "spray"]},
        "chemical_id": {"type": "integer"},
        "customer_id": {"type": "integer"},
    },
    "required": ["equipment_id", "field_id", "job_type", "customer_id"],
    "additionalProperties": False,
}


# ==========================================================
# Action → Input Schema Mapping
# ==========================================================

ACTION_INPUT_SCHEMAS = {
    # ===== MCP Tools =====
    "dispatch_equipment": DispatchEquipmentInput,
    "batch_dispatch": BatchDispatchInput,
    "process_payment": PaymentInput,
    "log_incident_note": IncidentInput,
    "generate_fleet_report": ReportInput,
    "equipment_status_snapshot": EmptyInput,
    "pesticide_compliance_policy": EmptyInput,
    "draft_delay_explanation": EmptyInput,

    # ===== RAG Tools =====
    "search_agricultural_knowledge": KnowledgeSearchInput,

    # ===== Terminal =====
    "escalate": EscalationInput,
    "end_conversation": FinalAnswerInput,
    "final_answer": FinalAnswerInput,
}

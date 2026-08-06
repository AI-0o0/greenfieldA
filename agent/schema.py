from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model


MAX_STEPS = 6
VALIDATION_RETRIES = 2

TERMINAL_ACTIONS = {
    "escalate",
    "end_conversation",
    "final_answer",
}


class AgentStep(BaseModel):
    """
    Runtime step produced by the agent.
    The actual model is rebuilt every turn so the `action`
    field always matches the currently available MCP tools.
    """

    thought: str
    action: str
    action_input: dict = Field(default_factory=dict)
    is_final: bool


def build_agent_step_model(action_names):
    """
    Build an AgentStep model whose `action` field is restricted
    to the MCP tools currently exposed by the server plus the
    terminal actions.
    """
    allowed = tuple(sorted(set(action_names) | TERMINAL_ACTIONS))

    return create_model(
        "AgentStep",
        thought=(str, ...),
        action=(Literal[allowed], ...),
        action_input=(dict, Field(default_factory=dict)),
        is_final=(bool, ...),
    )


# ==========================================================
# Base Input
# ==========================================================

class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyInput(StrictInput):
    """Tool takes no parameters."""
    pass


# ==========================================================
# Terminal Actions
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
    equipment_id: int
    field_id: int
    customer_id: int
    job_type: Literal["till", "harvest", "spray"]
    chemical_id: int | None = None


class BatchDispatchInput(StrictInput):
    equipment_ids: list[int]
    field_id: int


class PaymentInput(StrictInput):
    customer_id: int


class IncidentInput(StrictInput):
    raw_note: str


class ReportInput(StrictInput):
    month: str


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

    # ===== Terminal =====

    "escalate": EscalationInput,

    "end_conversation": FinalAnswerInput,

    "final_answer": FinalAnswerInput,
}
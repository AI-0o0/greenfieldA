"""
agent/schema.py

Agent-specific constants (MAX_STEPS, TERMINAL_ACTIONS), the dynamic
AgentStep model builder, and the system prompt factory.

All tool-input Pydantic schemas and the ACTION_INPUT_SCHEMAS mapping
now live in the shared ``schemas.tool_inputs`` module.
"""

from typing import Literal, Optional, List
from pydantic import BaseModel, Field, create_model

# ---- Re-export shared schemas so existing callers keep working ----
from schemas.tool_inputs import (
    StrictInput,
    EmptyInput,
    FinalAnswerInput,
    EscalationInput,
    DispatchEquipmentInput,
    BatchDispatchInput,
    PaymentInput,
    IncidentInput,
    ReportInput,
    KnowledgeSearchInput,
    SignoffResponse,
    DISPATCH_SCHEMA,
    ACTION_INPUT_SCHEMAS,
)

MAX_STEPS = 6

TERMINAL_ACTIONS = {
    "escalate",
    "end_conversation",
    "final_answer",
}

class AgentStep(BaseModel):
    """Runtime step produced by the agent."""

    thought: str
    action: str
    action_input: Optional[dict] = None
    plan_updated: bool = False
    new_plan: Optional[str] = None
    next_subgoal: Optional[str] = None
    is_final: bool = False


def build_agent_step_model(action_names: List[str]):
    """
    Build an AgentStep model whose action field is restricted
    to the MCP tools currently exposed by the server plus the
    terminal actions.
    """
    allowed = tuple(sorted(set(action_names) | TERMINAL_ACTIONS))

    return create_model(
        "AgentStep",
        thought=(str, ...),
        action=(Literal[allowed], ...),
        action_input=(dict, Field(default_factory=dict)),
        plan_updated=(bool, Field(default=False, description="True if the plan or subgoal was updated")),
        new_plan=(Optional[str], Field(default=None, description="Updated multi-step plan")),
        next_subgoal=(Optional[str], Field(default=None, description="Next subgoal to achieve")),
        is_final=(bool, Field(default=False, description="True if this is the final step")),
    )


def build_system_prompt(tool_names: List[str]) -> str:
    tool_list = "\n".join(sorted(tool_names))
    return f"""You are a constrained support agent for Greenfield Agriculture.

Available Tools:
{tool_list}

Strict Execution Instructions:
1. MANDATORY RAG SEARCH FOR KNOWLEDGE / POLICIES:
   - If the user asks about operating speeds, chemical rules, buffer zones, SOP codes, or equipment manuals, you MUST call 'search_agricultural_knowledge' FIRST to retrieve grounded document context before giving a final answer.
   - Never answer compliance or manual questions from memory without searching.

2. FLEET & EQUIPMENT STATUS:
   - When asked to check equipment or overall fleet status, do NOT talk about the tool in 'final_answer'. Set action to 'equipment_status_snapshot' immediately to fetch live data.
   - Do NOT invoke 'dispatch_equipment' or 'batch_dispatch' unless you are executing an actual job with explicit IDs.

3. MEMORY & USER FACTS:
   - When acknowledging user facts, preferences, or allergies (e.g. "Customer 1 is allergic to SPR-3001"), acknowledge them directly using 'final_answer'. Do NOT call 'log_incident_note' or other tools. Memory eviction and consolidation handle context automatically.
   - Only use 'log_incident_note' for actual physical farm emergencies, chemical spills, or equipment damage. When calling it, pass a single string field named 'raw_note'.

4. FINAL RESPONSES:
   - When you have enough information or need to respond directly to the user, set action to 'final_answer' and put your response message inside 'action_input.answer'.
   - Output clean, valid JSON strings for all tool arguments and responses.

Think step by step and return only the structured response."""
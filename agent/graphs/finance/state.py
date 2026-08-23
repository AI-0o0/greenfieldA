"""
agent/graphs/finance/state.py

State schemas and Pydantic structured output models for the Greenfield
Autonomous Finance & Lending State Graph Agent.
"""

from __future__ import annotations

from typing import TypedDict, Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


# ==============================================================================
# 1. Pydantic Structured Output Models
# ==============================================================================

class RouteDecision(BaseModel):
    """Routing classification for inbound farmer requests."""
    request_type: Literal["advice", "financing"] = Field(
        description="Route as 'advice' for financial planning/consultation, or 'financing' for loan/credit applications."
    )
    reasoning: str = Field(description="Explanation for the routing classification.")


class SpecialistDecision(BaseModel):
    """Specialist routing decision for operational domain inquiries."""
    specialist_type: Literal["equipment", "crop", "no"] = Field(
        description="'equipment' if machinery/depreciation, 'crop' if harvest/yield/inputs, or 'no' for general finance."
    )
    requires_human_escalation: bool = Field(
        default=False,
        description="True if the request involves specialized engineering/agronomy requiring human expert input."
    )
    reasoning: str = Field(description="Explanation for specialist selection.")


class GeneratedOptions(BaseModel):
    """Candidate financial options generated for the farmer."""
    options: List[Dict[str, Any]] = Field(
        description="List of 2 to 3 candidate financial strategies with name, description, estimated_cost, and pros_cons."
    )
    summary: str = Field(description="Overview of the options.")


class EligibilityEvaluation(BaseModel):
    """Credit and underwriting policy evaluation result."""
    is_eligible: bool = Field(description="True if applicant meets baseline credit and operational requirements.")
    reasons: List[str] = Field(description="List of eligibility criteria met or violated.")
    missing_requirements: List[str] = Field(default_factory=list, description="List of missing requirements if ineligible.")


class DocumentValidation(BaseModel):
    """Document completeness and authenticity validation."""
    is_valid: bool = Field(description="True if all required documents are present and valid.")
    missing_documents: List[str] = Field(default_factory=list, description="Names of missing required documents.")
    feedback: str = Field(description="Validation feedback for the applicant.")


class FinancialAnalysisResult(BaseModel):
    """Underwriting financial ratio and capacity analysis."""
    assessed_amount: float = Field(description="Assessed funding requirement in USD.")
    dscr: float = Field(description="Estimated Debt Service Coverage Ratio.")
    risk_level: Literal["low", "medium", "high"] = Field(description="Risk classification.")
    recommended_term_months: int = Field(description="Repayment horizon in months.")
    max_borrowing_capacity: float = Field(description="Maximum safe debt ceiling.")


class AlternativeOptionsResult(BaseModel):
    """Fallback financial or operational alternatives when loan terms are rejected/declined."""
    alternatives: List[Dict[str, Any]] = Field(description="Alternative financing or operational options.")
    rationale: str = Field(description="Reasoning for why these alternatives are viable.")


# ==============================================================================
# 2. Main State Graph State Schema (TypedDict)
# ==============================================================================

class FinanceState(TypedDict, total=False):
    """
    Complete state container for the Greenfield Autonomous Finance Graph.
    Persisted durably to SQLite at each transition boundary.
    """
    # Ingestion & Farmer Info
    thread_id: Optional[str]
    farmer_id: Optional[int]
    farmer_name: Optional[str]
    farmer_request: str
    request_type: Optional[Literal["advice", "financing"]]
    execution_log: List[str]

    # Financial Advice Path
    financial_context: Dict[str, Any]
    specialist_type: Optional[Literal["equipment", "crop", "no"]]
    specialist_data: Dict[str, Any]
    specialist_escalated: bool
    financial_options: List[Dict[str, Any]]
    tot_evaluation: Dict[str, Any]
    rag_policies: List[str]
    recommendation: Optional[str]

    # Financing Application Path
    application_id: Optional[int]
    eligibility_status: Optional[bool]
    eligibility_reasons: List[str]
    eligibility_rag_docs: List[str]
    rejection_reason: Optional[str]
    documents_required: List[str]
    documents_submitted: Dict[str, Any]
    documents_valid: Optional[bool]
    validation_feedback: Optional[str]

    # Analysis, HITL & Provider
    financial_analysis: Dict[str, Any]
    tot_financing_options: List[Dict[str, Any]]
    tot_financing_evaluation: Dict[str, Any]
    hitl_required: bool
    hitl_task_id: Optional[int]
    admin_decision: Optional[Literal["approve", "reject", "more_info"]]
    admin_feedback: Optional[str]
    submitted_application: Dict[str, Any]
    provider_response: Optional[Literal["approved", "rejected", "more_info"]]
    provider_terms: Dict[str, Any]
    farmer_accepts: Optional[bool]
    alternative_options: Optional[List[Dict[str, Any]]]
    process_result: Dict[str, Any]
    transaction_verification: Dict[str, Any]

    # Failure / Ticket System & Final Outputs
    current_step: str
    final_output: Optional[str]
    error: Optional[str]
    error_traceback: Optional[str]
    failed_node: Optional[str]
    ticket_id: Optional[int]
    retry_count: Optional[int]
    simulated_error_node: Optional[str]
    simulated_error_message: Optional[str]

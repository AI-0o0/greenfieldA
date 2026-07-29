import asyncio
import mcp.types as types
from typing import Literal, Optional, List
from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict
import sqlite3
import os
import jsonschema
from jsonschema.exceptions import ValidationError

mcp = FastMCP("Greenfield-Dispatch-Server")

# ============================================
# Repository Layer (Clean Architecture)
# ============================================
def get_db_connection():
    db_path = os.path.join("../db", "farm.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

class CustomerRepo:
    @staticmethod
    def get_customer(customer_id: int):
        with get_db_connection() as conn:
            return conn.execute("SELECT * FROM CUSTOMERS WHERE customer_id = ?", (customer_id,)).fetchone()

    @staticmethod
    def clear_credit_hold(customer_id: int):
        with get_db_connection() as conn:
            conn.execute("UPDATE CUSTOMERS SET credit_hold = 0 WHERE customer_id = ?", (customer_id,))
            conn.commit()

class EquipmentRepo:
    @staticmethod
    def get_equipment(eq_id: int):
        with get_db_connection() as conn:
            return conn.execute("SELECT * FROM EQUIPMENT WHERE equipment_id = ?", (eq_id,)).fetchone()

    @staticmethod
    def update_status(eq_id: int, status: str):
        with get_db_connection() as conn:
            conn.execute("UPDATE EQUIPMENT SET status = ? WHERE equipment_id = ?", (status, eq_id))
            conn.commit()

# ============================================
# Models 
# ============================================
class DispatchInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    equipment_id: int = Field(description="ID of the equipment to dispatch")
    field_id: int = Field(description="The target field ID")
    job_type: Literal["till", "harvest", "spray"] = Field(description="Type of job to perform")
    chemical_id: Optional[int] = Field(default=None, description="Required only when job_type is spray")
    customer_id: int = Field(description="ID of the authenticated customer")

class SignoffResponse(BaseModel):
    approved: bool = Field(description="Whether the human approves this chemical dispatch")
    notes: Optional[str] = Field(default=None, description="Optional reasoning for the decision")

class BatchDispatchInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    equipment_ids: List[int] = Field(description="List of equipment IDs to dispatch")
    field_id: int = Field(description="The target field ID for the batch job")

class IncidentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    raw_note: str = Field(description="Unstructured incident note from the field")

class PaymentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    customer_id: int = Field(description="ID of the customer making the payment")

# ============================================
# TASK 7: Runtime Notifications (Credit Hold Logic)
# ============================================
@mcp.tool()
async def process_payment(input_data: PaymentInput, ctx: Context) -> str:
    """Process a customer payment to clear their credit hold and unlock dispatch tools."""
    customer = CustomerRepo.get_customer(input_data.customer_id)
    if not customer:
        raise ValueError(f"Customer {input_data.customer_id} not found.")

    # 1. Update Real State in Database
    CustomerRepo.clear_credit_hold(input_data.customer_id)
    
    # 2. Trigger Notification (Task 7 Requirement)
    await ctx.session.send_tool_list_changed()
    
    return f"SUCCESS: Payment processed. Credit hold cleared for customer {input_data.customer_id}. Dispatch tools are now unlocked."

# ============================================
# TASK 8: Progress Tracking & Sampling
# ============================================
@mcp.tool()
async def batch_dispatch(input_data: BatchDispatchInput, ctx: Context) -> str:
    """Batch-dispatch multiple pieces of equipment. Emits real DB progress updates."""
    total_items = len(input_data.equipment_ids)
    progress_token = getattr(ctx.request_context.meta, "progressToken", None) if hasattr(ctx, "request_context") else None

    # Real Progress Tracking: Updating Database state
    for i, eq_id in enumerate(input_data.equipment_ids):
        # Update physical equipment status in DB
        EquipmentRepo.update_status(eq_id, "dispatched")
        await asyncio.sleep(0.5) # Simulate the IoT network delay
        
        if progress_token:
            await ctx.session.send_progress(
                progress_token=progress_token,
                progress=i + 1,
                total=total_items
            )
            
    return f"SUCCESS: Batch dispatch completed. {total_items} units sent to field {input_data.field_id}."

@mcp.tool()
async def log_incident_note(input_data: IncidentInput, ctx: Context) -> str:
    """Log an unstructured incident note and structure it using LLM sampling."""
    try:
        sampling_result = await ctx.session.create_message(
            messages=[
                types.SamplingMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=f"Structure this incident note into a concise summary and determine severity: {input_data.raw_note}"
                    )
                )
            ],
            max_tokens=200
        )
        
        if sampling_result and sampling_result.content:
            llm_response = sampling_result.content.text if isinstance(sampling_result.content, types.TextContent) else str(sampling_result.content)
        else:
            llm_response = "Structured parsing failed."
    except Exception as e:
        llm_response = f"Sampling error: {str(e)}"

    return f"Incident logged. Structured Output: {llm_response}"

# ============================================
# TASK 4, 5, 6: Dispatch & Elicitation 
# ============================================
# Explicit JSON Schema Definition for Defensive Design
DISPATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "equipment_id": {"type": "integer"},
        "field_id": {"type": "integer"},
        "job_type": {"type": "string", "enum": ["till", "harvest", "spray"]},
        "chemical_id": {"type": "integer"},
        "customer_id": {"type": "integer"}
    },
    "required": ["equipment_id", "field_id", "job_type", "customer_id"],
    "additionalProperties": False
}

@mcp.tool()
async def dispatch_equipment(input_data: DispatchInput, ctx: Context) -> str:
    """Dispatch a piece of equipment to perform a job on a specific field."""
    
    # Task 4 Defensive Design: Explicit Server-Side Validation independent of Pydantic
    try:
        jsonschema.validate(instance=input_data.model_dump(exclude_none=True), schema=DISPATCH_SCHEMA)
    except ValidationError as e:
        raise ValueError(f"SECURITY BLOCK: Schema validation failed. {e.message}")

    eq_id = input_data.equipment_id
    f_id = input_data.field_id
    job = input_data.job_type
    chem_id = input_data.chemical_id
    req_by = input_data.customer_id

    # Task 6: Capability Negotiation Check
    client_caps = ctx.session.client_capabilities
    has_elicitation = client_caps and client_caps.experimental and "elicitation" in client_caps.experimental
    if not has_elicitation:
        raise RuntimeError("SECURITY BLOCK: Client lacks elicitation capability.")

    if job == "spray" and not chem_id:
        raise ValueError("chemical_type is required for spray jobs.")

    # Task 7 Gate: Check Credit Hold BEFORE allowing dispatch
    customer = CustomerRepo.get_customer(req_by)
    if not customer:
        raise ValueError("Customer not found.")
    if customer["credit_hold"]:
        raise PermissionError("SECURITY BLOCK: Customer has an active credit hold. Dispatch denied.")

    # Validation & Equipment Checking
    equipment = EquipmentRepo.get_equipment(eq_id)
    if not equipment or equipment["status"] != "idle":
        raise ValueError("Equipment unavailable or not in idle state.")

    # Task 5: Elicitation Logic (Human-in-the-loop)
    if job == "spray" and chem_id:
        with get_db_connection() as conn:
            chemical = conn.execute("SELECT * FROM Chemicals WHERE chemical_id = ?", (chem_id,)).fetchone()
            
        if chemical and chemical["requires_signoff"] == 1:
            result = await ctx.elicit(
                message=f"DANGER: Approve dispatching autonomous equipment {eq_id} with restricted chemical?",
                response_type=SignoffResponse,
            )
            if result.action == "accept" and not result.data.approved:
                raise ValueError(f"Denied by Human: {result.data.notes}")
            elif result.action != "accept":
                raise RuntimeError("Sign-off cancelled or declined.")

    # Execute Dispatch
    EquipmentRepo.update_status(eq_id, "dispatched")
    return f"SUCCESS: Autonomous Equipment {eq_id} successfully dispatched to field {f_id}."
        
if __name__ == "__main__":
    mcp.run(transport='stdio')

import asyncio
import mcp.types as types
from typing import Literal, Optional, List
from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict
import sqlite3
import os

mcp = FastMCP("Greenfield-Dispatch-Server")

# Global state for Task 7
technician_authenticated = False

def get_db_connection():
    db_path = os.path.join("../db", "farm.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# --- Teammate's Models ---
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

# --- Task 7 & 8 Models ---
class AuthInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    technician_id: int = Field(description="ID of the technician to authenticate")

class OverrideInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    equipment_id: int = Field(description="ID of the equipment to override emergency stop")

class BatchDispatchInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    equipment_ids: List[int] = Field(description="List of equipment IDs to dispatch")
    field_id: int = Field(description="The target field ID for the batch job")

class IncidentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    raw_note: str = Field(description="Unstructured incident note from the field")


# ============================================
# TASK 7: Runtime Notifications
# ============================================
@mcp.tool()
async def authenticate_technician(input_data: AuthInput, ctx: Context) -> str:
    """Authenticate to update the current state and unlock restricted tools mid-session."""
    global technician_authenticated
    technician_authenticated = True
    
    # Task 7 Acceptance Criteria: Push tools/list_changed notification
    await ctx.session.send_tool_list_changed()
    return f"Technician {input_data.technician_id} authenticated. Emergency override tool unlocked."

@mcp.tool()
async def override_emergency_stop(input_data: OverrideInput, ctx: Context) -> str:
    """Override an emergency stop on a piece of equipment (Requires Authentication)."""
    if not technician_authenticated:
        raise ValueError("SECURITY BLOCK: Unauthorized. Authenticate first.")
    return f"Emergency stop overridden for equipment {input_data.equipment_id}."

# ============================================
# TASK 8: Progress Tracking & Sampling
# ============================================
@mcp.tool()
async def batch_dispatch(input_data: BatchDispatchInput, ctx: Context) -> str:
    """Batch-dispatch multiple pieces of equipment. Emits progress updates."""
    total_items = len(input_data.equipment_ids)
    progress_token = getattr(ctx.request_context.meta, "progressToken", None) if hasattr(ctx, "request_context") else None

    # Task 8 Acceptance Criteria: Emit intermediate progress updates
    for i, eq_id in enumerate(input_data.equipment_ids):
        await asyncio.sleep(1) 
        if progress_token:
            await ctx.session.send_progress(
                progress_token=progress_token,
                progress=i + 1,
                total=total_items
            )
            
    return f"Batch dispatch completed for {total_items} equipment units to field {input_data.field_id}."

@mcp.tool()
async def log_incident_note(input_data: IncidentInput, ctx: Context) -> str:
    """Log an unstructured incident note and structure it using LLM sampling."""
    try:
        # Task 8 Acceptance Criteria: sampling/createMessage call
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
# TEAMMATE WORK: TASK 4, 5, 6
# ============================================
@mcp.tool()
async def dispatch_equipment(input_data: DispatchInput, ctx: Context) -> str:
    """Dispatch a piece of equipment to perform a job on a specific field."""
    eq_id = input_data.equipment_id
    f_id = input_data.field_id
    job = input_data.job_type
    chem_id = input_data.chemical_id
    req_by = input_data.customer_id
    chemical_name = None

    client_caps = ctx.session.client_capabilities
    has_elicitation = client_caps and client_caps.experimental and "elicitation" in client_caps.experimental
    if not has_elicitation:
        raise RuntimeError("SECURITY BLOCK: Client lacks elicitation capability.")

    if job == "spray" and not chem_id:
        raise ValueError("chemical_type is required for spray jobs.")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM Customers WHERE customer_id = ?", (req_by,))
        if not cursor.fetchone():
            raise ValueError("Customer not found.")

        cursor.execute("SELECT * FROM Fields WHERE field_id = ?", (f_id,))
        field = cursor.fetchone()
        if not field or field["customer_id"] != req_by:
            raise ValueError("Field validation failed.")

        cursor.execute("SELECT * FROM Equipment WHERE equipment_id = ?", (eq_id,))
        equipment = cursor.fetchone()
        if not equipment or equipment["status"] != "idle":
            raise ValueError("Equipment unavailable.")

        if job == "spray" and chem_id:
            cursor.execute("SELECT * FROM Chemicals WHERE chemical_id = ?", (chem_id,))
            chemical = cursor.fetchone()
            
            if chemical and chemical["requires_signoff"] == 1:
                result = await ctx.elicit(
                    message=f"DANGER: Approve dispatching equipment {eq_id} with restricted chemical?",
                    response_type=SignoffResponse,
                )
                if result.action == "accept" and not result.data.approved:
                    raise ValueError(f"Denied: {result.data.notes}")
                elif result.action != "accept":
                    raise RuntimeError("Sign-off cancelled or declined.")

        msg = f"SUCCESS: Equipment {eq_id} dispatched."
    finally:
        conn.close()
        
    return msg
        
if __name__ == "__main__":
    mcp.run(transport='stdio')

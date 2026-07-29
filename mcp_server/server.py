import asyncio
import mcp.types as types
from typing import Literal, Optional
from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict
import sqlite3
import os

mcp = FastMCP("Greenfield-Dispatch-Server")

# ============================================
# TASK 7: Global state for authentication
# ============================================
technician_authenticated = False

# connect the server with database
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

# --- Your New Models (Tasks 7 & 8) ---
class AuthInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    technician_id: int = Field(description="ID of the technician to authenticate")

class ReportInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    month: str = Field(description="The month to generate the fleet report for (e.g., '2023-10')")

class IncidentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    raw_note: str = Field(description="The verbose, raw incident note submitted by a technician")

class ApproveDispatchInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dispatch_id: int = Field(description="ID of the dispatch job to approve")


# ============================================
# YOUR WORK: TASK 7 - Runtime Notifications
# ============================================
@mcp.tool()
async def authenticate_technician(input_data: AuthInput, ctx: Context) -> str:
    """Authenticate a technician to unlock restricted tools dynamically."""
    global technician_authenticated
    technician_authenticated = True
    
    # Trigger the tools/list_changed notification mid-session
    await ctx.session.send_tool_list_changed()
    return f"SUCCESS: Technician {input_data.technician_id} authenticated. Restricted tools (like approve_dispatch_job) are now unlocked."

@mcp.tool()
async def approve_dispatch_job(input_data: ApproveDispatchInput, ctx: Context) -> str:
    """Approve a restricted chemical dispatch job (Requires Authentication)."""
    if not technician_authenticated:
        raise ValueError("SECURITY BLOCK: Unauthorized. You must authenticate as a technician first.")
    return f"SUCCESS: Dispatch job {input_data.dispatch_id} approved."

# ============================================
# YOUR WORK: TASK 8 - Progress Tracking & Sampling
# ============================================
@mcp.tool()
async def generate_fleet_report(input_data: ReportInput, ctx: Context) -> str:
    """Generate a monthly fleet utilization report. This is a long-running batch process."""
    # Get progress token if the client sent one
    progress_token = getattr(ctx.request_context.meta, "progressToken", None) if hasattr(ctx, "request_context") else None

    # Simulate a long-running database scan and report progress
    for i in range(1, 5):
        await asyncio.sleep(1) # simulate waiting for database queries
        if progress_token:
            await ctx.session.send_progress(
                progress_token=progress_token,
                progress=i * 25,
                total=100
            )
    return f"SUCCESS: Fleet report for {input_data.month} generated successfully (100% complete)."

@mcp.tool()
async def log_incident_note(input_data: IncidentInput, ctx: Context) -> str:
    """Log an incident note. Uses LLM sampling to summarize the note and extract severity."""
    try:
        # Trigger sampling/createMessage to ask the client's LLM to process the unstructured text
        sampling_result = await ctx.session.create_message(
            messages=[
                types.SamplingMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=f"Please summarize this incident concisely and output its severity (Low, Medium, or High). Input Note: {input_data.raw_note}"
                    )
                )
            ],
            max_tokens=150
        )
        
        # Extract the string response from the LLM
        if sampling_result and sampling_result.content:
            if isinstance(sampling_result.content, types.TextContent):
                llm_response = sampling_result.content.text
            else:
                llm_response = str(sampling_result.content)
        else:
            llm_response = "Unknown Severity (Fallback)."
    except Exception as e:
        llm_response = f"Sampling failed: {str(e)}"

    return f"SUCCESS: Incident logged. LLM Analysis: {llm_response}"


# ============================================
# TEAMMATE WORK: TASK 4, 5, 6 
# ============================================
@mcp.tool()
async def dispatch_equipment(input_data: DispatchInput, ctx: Context) -> str:
    """Dispatch a piece of equipment to perform a job on a specific field."""
    
    # Data extraction
    eq_id = input_data.equipment_id
    f_id = input_data.field_id
    job = input_data.job_type
    chem_id = input_data.chemical_id
    req_by = input_data.customer_id
    chemical_name = None

    # ============================================
    # TASK 6: Capability Negotiation (Elicitation Gating)
    # ============================================
    client_caps = ctx.session.client_capabilities
    has_elicitation = client_caps and client_caps.experimental and "elicitation" in client_caps.experimental
    
    if not has_elicitation:
        raise RuntimeError("SECURITY BLOCK: Client does not support elicitation. The dispatch_equipment tool is strictly disabled for this client.")

    # ============================================
    # TASK 4: Defensive Tool Design for Dispatch
    # ============================================
    
    # Validation 1
    if job == "spray" and not chem_id:
        raise ValueError("chemical_type is required for chemical_spray jobs.")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Validation 2: Does the customer exist?
        cursor.execute("SELECT * FROM Customers WHERE customer_id = ?", (req_by,))
        customer = cursor.fetchone()
        if not customer:
            raise ValueError(f"Customer {req_by} not found in database.")

        # Validation 3: Does the field exist?
        cursor.execute("SELECT * FROM Fields WHERE field_id = ?", (f_id,))
        field = cursor.fetchone()
        if not field:
            raise ValueError(f"Field {f_id} does not exist.")

        # validation 4: Does this filed owened by the customer?
        actual_owner = field["customer_id"]
        if actual_owner != req_by:
            raise ValueError(f"SECURITY BLOCK: Dispatch request could not be validated. Field does not exist or does not belong to you.")

        # Validation 5: Does the equipment exist?
        cursor.execute("SELECT * FROM Equipment WHERE equipment_id = ?", (eq_id,))
        equipment = cursor.fetchone()
        if not equipment:
            raise ValueError(f"Equipment {eq_id} does not exist.")
    
        # validation 6: Check the eqyipment status
        eq_status = equipment["status"]
        if eq_status != "idle":
            raise ValueError(f"Equipment {eq_id} cannot be dispatched. Current status is: '{eq_status}'.")

        # =========================================
        # TASK 5: Chemical Application Elicitation
        # =========================================
        if job == "spray" and chem_id:
            cursor.execute("SELECT * FROM Chemicals WHERE chemical_id = ?", (chem_id,))
            chemical = cursor.fetchone()
            
            # if a danger chemical 
            if chemical and chemical["requires_signoff"] == 1:
                # send a request to the user
                result = await ctx.elicit(
                    message=(
                        f"DANGER: Chemical '{chemical['name']}' is restricted."
                        f"Approve dispatching equipment {eq_id} to field {f_id}?"
                    ),
                    response_type=SignoffResponse,
                )

                if result.action == "accept":
                    if not result.data.approved:
                        raise ValueError(
                            f"Dispatch denied by human reviewer"
                            + (f": {result.data.notes}" if result.data.notes else ".")
                        )
                    # approved — fall through to dispatch
                elif result.action == "decline":
                    raise ValueError("Human declined to review this dispatch request.")
                else:  # "cancel"
                    raise RuntimeError("Sign-off request was cancelled before a decision was made.")
        # =========================================

        # --- Success ---    
        msg = f"SUCCESS: Equipment {eq_id} dispatched to field {f_id} for {job}."
        if chemical_name:
            msg += f" (Chemical applied: {chemical_name})"
        elif chem_id:
            msg += f" (Chemical ID applied: {chem_id})"

    finally:
        conn.close()
        return msg
        
if __name__ == "__main__":
    mcp.run(transport='stdio')

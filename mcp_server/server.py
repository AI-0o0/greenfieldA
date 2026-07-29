from typing import Literal, Optional
from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field, ConfigDict
import sqlite3
import os

mcp = FastMCP("Greenfield-Dispatch-Server")

# connect the server with database
def get_db_connection():
    db_path = os.path.join("../db", "farm.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

class DispatchInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    equipment_id: int = Field(description="ID of the equipment to dispatch")
    field_id: int = Field(description="The target field ID")
    job_type: Literal["till", "harvest", "spray"] = Field(
        description="Type of job to perform"
    )
    chemical_id: Optional[int] = Field(
        default=None, 
        description="Required only when job_type is spray"
    )
    customer_id: int = Field(description="ID of the authenticated customer")

# --- The response shape FastMCP will ask the client to fill in ---
class SignoffResponse(BaseModel):
    approved: bool = Field(description="Whether the human approves this chemical dispatch")
    notes: Optional[str] = Field(default=None, description="Optional reasoning for the decision")


# The Tool & Logic
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
        
if __name__ == "__main__":
    mcp.run(transport='stdio')
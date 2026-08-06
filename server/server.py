import os
import sys
import sqlite3
import asyncio
import jsonschema
import mcp.types as types 
from fastmcp import FastMCP , Context
from typing import Literal, Optional, List
from mcp.types import ElicitRequestedSchema
from pydantic import BaseModel, Field, ConfigDict

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.append(parent_dir)

# Initialize FastMCP server for Greenfield
mcp = FastMCP("Greenfield-Dispatch-Server")

def get_db_connection():
    # Fallback path creation if db folder is missing
    db_dir = os.path.join(os.path.dirname(__file__), "..", "db")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.environ.get("GREENFIELD_DB_PATH") or os.path.join(db_dir, "farm.db")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    # Ensure basic tables exist to prevent crashes during test
    conn.execute("CREATE TABLE IF NOT EXISTS CUSTOMERS (customer_id INTEGER PRIMARY KEY, credit_hold INTEGER)")
    conn.execute("CREATE TABLE IF NOT EXISTS EQUIPMENT (equipment_id INTEGER PRIMARY KEY, status TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS CHEMICALS (chemical_id INTEGER PRIMARY KEY, requires_signoff INTEGER)")
    conn.commit()
    return conn

class PaymentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    customer_id: int = Field(description="ID of the customer making the payment")

class BatchDispatchInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    equipment_ids: List[int] = Field(description="List of equipment IDs to dispatch")
    field_id: int = Field(description="The target field ID for the batch job")

class IncidentInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    raw_note: str = Field(description="Unstructured incident note from the field")

class DispatchInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    equipment_id: int = Field(description="ID of the equipment to dispatch")
    field_id: int = Field(description="The target field ID")
    job_type: Literal["till", "harvest", "spray"] = Field(description="Type of job to perform")
    chemical_id: Optional[int] = Field(default=None, description="Required only when job_type is spray")
    customer_id: int = Field(description="ID of the authenticated customer")

class SignoffResponse(BaseModel):
    approved: bool = Field(description="Whether the human approves this chemical dispatch")
    notes: str = Field(default="", description="Optional reasoning for the decision")


#============================================
# Tools
#============================================
@mcp.tool()
async def process_payment(input_data: PaymentInput, ctx: Context) -> str:
    """Process a customer payment to clear their credit hold and unlock dispatch tools."""
    with get_db_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO CUSTOMERS (customer_id, credit_hold) VALUES (?, 0)", (input_data.customer_id,))
        conn.execute("UPDATE CUSTOMERS SET credit_hold = 0 WHERE customer_id = ?", (input_data.customer_id,))
        conn.commit()
    
    await ctx.session.send_tool_list_changed()
    return f"SUCCESS: Payment processed. Credit hold cleared for customer {input_data.customer_id}."

@mcp.tool()
async def batch_dispatch(input_data: BatchDispatchInput, ctx: Context) -> str:
    """Batch-dispatch multiple pieces of equipment with progress updates."""
    total_items = len(input_data.equipment_ids)
    progress_token = getattr(getattr(ctx, "request_context", None), "progressToken", None)

    with get_db_connection() as conn:
        for i, eq_id in enumerate(input_data.equipment_ids):
            conn.execute("UPDATE Equipment SET status = 'dispatched' WHERE equipment_id = ?", (eq_id,))
            conn.commit()
            await asyncio.sleep(0.2)
            
            if progress_token:
                await ctx.session.send_progress(
                    progress_token=progress_token,
                    progress=i + 1,
                    total=total_items
                )
            
    return f"SUCCESS: Batch dispatch completed for {total_items} units to field {input_data.field_id}."

@mcp.tool()
async def log_incident_note(input_data: IncidentInput, ctx: Context) -> str:
    """Log an unstructured incident note and structure it using LLM sampling."""
    try:
        sampling_result = await ctx.session.create_message(
            messages=[
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": f"Structure this incident note into a concise summary and determine severity: {input_data.raw_note}"
                    }
                }
            ],
            max_tokens=200
        )
        llm_response = sampling_result.content.text if sampling_result and sampling_result.content else "Parsed."
    except Exception as e:
        llm_response = f"Sampling failed: {str(e)} | Note recorded: {input_data.raw_note}"

    return f"Incident logged. Structured Output: {llm_response}"


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

    # Schema-level validation (types/shape, independent of the checks below)
    try:
        jsonschema.validate(instance=input_data.model_dump(exclude_none=True), schema=DISPATCH_SCHEMA)
    except ValidationError as e:
        raise ValueError(f"SECURITY BLOCK: Schema validation failed. {e.message}")

    eq_id = input_data.equipment_id
    f_id = input_data.field_id
    job = input_data.job_type
    chem_id = input_data.chemical_id
    req_by = input_data.customer_id

    has_elicitation = ctx.session.check_client_capability(
        types.ClientCapabilities(elicitation=types.ElicitationCapability())
    )

    if not has_elicitation:
        raise RuntimeError(
            "SECURITY BLOCK: Client does not support elicitation. "
            "The dispatch_equipment tool is strictly disabled for this client."
        )

    if job == "spray" and not chem_id:
        raise ValueError("chemical_id is required for spray jobs.")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Validation: does the customer exist?
        cursor.execute("SELECT * FROM Customers WHERE customer_id = ?", (req_by,))
        customer = cursor.fetchone()
        if not customer:
            raise ValueError(f"Customer {req_by} not found in database.")

        # Validation: does the field exist?
        cursor.execute("SELECT * FROM Fields WHERE field_id = ?", (f_id,))
        field = cursor.fetchone()
        if not field:
            raise ValueError(f"Field {f_id} does not exist.")

        # Validation: is this field owned by the requesting customer?
        actual_owner = field["customer_id"]
        if actual_owner != req_by:
            raise ValueError(
                "SECURITY BLOCK: Dispatch request could not be validated. "
                "Field does not exist or does not belong to you."
            )

        # Validation: does the equipment exist?
        cursor.execute("SELECT * FROM Equipment WHERE equipment_id = ?", (eq_id,))
        equipment = cursor.fetchone()
        if not equipment:
            raise ValueError(f"Equipment {eq_id} does not exist.")

        # Validation: is the equipment idle?
        eq_status = equipment["status"]
        if eq_status != "idle":
            raise ValueError(f"Equipment {eq_id} cannot be dispatched. Current status is: '{eq_status}'.")

        chemical_name = None
        signoff_approved = False
        if job == "spray" and chem_id:
            cursor.execute("SELECT * FROM Chemicals WHERE chemical_id = ?", (chem_id,))
            chemical = cursor.fetchone()
            if not chemical:
                raise ValueError(f"Chemical {chem_id} does not exist.")

            chemical_name = chemical["name"]

            if chemical["requires_signoff"] == 1:
                result = await ctx.elicit(
                    message=(
                        f"DANGER: Chemical '{chemical['name']}' is restricted. "
                        f"Approve dispatching equipment {eq_id} to field {f_id}?"
                    ),
                    response_type=SignoffResponse,
                )

                if result.action == "accept":
                    if not result.data.approved:
                        raise ValueError(
                            "Dispatch denied by human reviewer"
                            + (f": {result.data.notes}" if result.data.notes else ".")
                        )
                    signoff_approved = True
                    # approved — fall through to dispatch
                elif result.action == "decline":
                    raise ValueError("Human declined to review this dispatch request.")
                else:  # "cancel"
                    raise RuntimeError("Sign-off request was cancelled before a decision was made.")
        # =========================================

        # --- Success: record the dispatch in the DB ---
        cursor.execute(
            "SELECT technician_id FROM Technicians "
            "WHERE role = 'dispatcher' AND authenticated = 1 "
            "ORDER BY technician_id LIMIT 1"
        )
        tech_row = cursor.fetchone()
        tech_id = tech_row["technician_id"] if tech_row else 1

        approval_status = "approved" if signoff_approved else "not_required"
        approved_by = tech_id if signoff_approved else None

        cursor.execute(
            """
            INSERT INTO Dispatch_Jobs
                (equipment_id, field_id, technician_id, job_type, chemical_id,
                 status, approval_status, approved_by, started_at)
            VALUES (?, ?, ?, ?, ?, 'dispatched', ?, ?, CURRENT_TIMESTAMP)
            """,
            (eq_id, f_id, tech_id, job, chem_id, approval_status, approved_by),
        )
        dispatch_id = cursor.lastrowid
        cursor.execute(
            "UPDATE Equipment SET status = 'dispatched' WHERE equipment_id = ?",
            (eq_id,),
        )
        conn.commit()

        msg = (
            f"SUCCESS: Equipment {eq_id} dispatched to field {f_id} for {job} "
            f"(dispatch #{dispatch_id})."
        )
        if chemical_name:
            msg += f" (Chemical applied: {chemical_name})"

        return msg

    finally:
        conn.close()


# ============================================
# Resources
# ============================================

PESTICIDE_COMPLIANCE_POLICY = """\
GREENFIELD AGRICULTURE — RESTRICTED CHEMICAL APPLICATION POLICY (v1.2)

1. Buffer zones
   - Minimum 15 meters from any waterway, canal, or irrigation channel
     for 'restricted' hazard-class chemicals.
   - Minimum 8 meters from any waterway for 'controlled' hazard-class
     chemicals.
   - No buffer zone required for 'low' hazard-class products.

2. Wind conditions
   - No spray application of 'restricted' or 'controlled' chemicals
     when sustained wind exceeds 15 km/h.

3. Sign-off requirement
   - Any dispatch job carrying a chemical flagged requires_signoff = 1
     in the Chemicals table must receive explicit human sign-off before
     the equipment is dispatched.

4. Record-keeping
   - Every restricted or controlled application must be logged with
     technician ID, field ID, and timestamp in Dispatch_Jobs.

5. Emergency response
   - If a restricted-chemical job triggers an equipment fault or leak,
     the technician must call emergency_stop immediately and file an
     Incident_Notes entry before the equipment can be redispatched.
"""


@mcp.resource("policy://pesticide-compliance")
def pesticide_compliance_policy() -> str:
    """Read-only compliance document covering buffer zones, wind limits,
    sign-off rules, and record-keeping for restricted/controlled chemical
    applications. Exposed as a resource (not a tool) because it's a
    static reference the model should read once and reason over, not an
    action it invokes."""
    return PESTICIDE_COMPLIANCE_POLICY


@mcp.resource("fleet://equipment-status")
def equipment_status_snapshot() -> str:
    """Read-only current-status snapshot of every machine in the fleet
    (idle/dispatched/maintenance/offline + location). Modeled as a
    resource because it's a record the model fetches to get its
    bearings before deciding what to do, not a parameterized action."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT equipment_id, serial_number, equipment_type, status, current_location
            FROM Equipment
            ORDER BY equipment_id
            """
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    header = "equipment_id | serial_number | type | status | location"
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(
            f"{r['equipment_id']} | {r['serial_number']} | {r['equipment_type']} | "
            f"{r['status']} | {r['current_location']}"
        )
    return "\n".join(lines)


# ============================================
# Prompts
# ============================================
@mcp.prompt()
def draft_delay_explanation(dispatch_id: int) -> str:
    """Reusable, parameterized starting point for a common dispatcher
    task: explaining a delayed job to the customer. The host surfaces
    this via prompts/list so dispatchers don't have to re-invent the
    wording every time, and it's filled in with the real job details
    instead of the model guessing them."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT d.dispatch_id, d.job_type, d.status, d.requested_at,
                   f.field_name, c.company_name
            FROM Dispatch_Jobs d
            JOIN Fields f ON d.field_id = f.field_id
            JOIN Customers c ON f.customer_id = c.customer_id
            WHERE d.dispatch_id = ?
            """,
            (dispatch_id,),
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row:
        return (
            f"No dispatch job found with ID {dispatch_id}. Ask the user to "
            f"confirm the dispatch ID before drafting anything."
        )

    return (
        f"Draft a short, professional message to {row['company_name']} "
        f"explaining that their {row['job_type']} job (dispatch #{row['dispatch_id']}) "
        f"on field '{row['field_name']}', requested at {row['requested_at']}, is "
        f"currently '{row['status']}' and running behind schedule. Apologize "
        f"briefly, do not over-promise a new time, and offer to follow up once "
        f"the equipment is confirmed. Keep it under 80 words."
    )

  
if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport == "stdio":
        sys.stderr.write("Starting Greenfield Server [stdio]...")
        mcp.run(transport="stdio")
    elif transport == "http":
        sys.stderr.write("Starting Greenfield Server [http:8080]...")
        mcp.run(transport="streamable-http", host="0.0.0.0", port=8080)
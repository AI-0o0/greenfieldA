from typing import Literal, Optional
from fastmcp import FastMCP
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
        description="Required only when job_type is chemical_spray"
    )
    
    customer_id: int = Field(description="ID of the authenticated customer")

# The Tool & Logic
@mcp.tool()
async def dispatch_equipment(input_data: DispatchInput) -> str:
    """Dispatch a piece of equipment to perform a job on a specific field."""
    # Data extraction
    eq_id = input_data.equipment_id
    f_id = input_data.field_id
    job = input_data.job_type
    chem = input_data.chemical_id
    req_by = input_data.customer_id

    # Validation 1
    if job == "spray" and not chem:
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
            raise ValueError(f"SECURITY BLOCK: Field {f_id} does not belong to the requesting customer {req_by}.")

        # Validation 5: Does the equipment exist?
        cursor.execute("SELECT * FROM Equipment WHERE id = ?", (eq_id,))
        equipment = cursor.fetchone()
        if not equipment:
            raise ValueError(f"Equipment {eq_id} does not exist.")
    
        # validation 6: Check the eqyipment status
        eq_status = equipment["status"]
        if eq_status != "idle":
            raise ValueError(f"Equipment {eq_id} cannot be dispatched. Current status is: '{eq_status}'.")

        # --- Success ---    
        msg = f"SUCCESS: Equipment {eq_id} dispatched to field {f_id} for {job}."
        if chem:
            msg += f" (Chemical applied: {chem})"
        return msg

    finally:
        conn.close()
        
if __name__ == "__main__":
    mcp.run(transport='stdio')
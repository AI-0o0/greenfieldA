from typing import Literal, Optional
from fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict

mcp = FastMCP("Greenfield-Dispatch-Server")


CUSTOMERS = {
    101: {"name": "Ahmed", "status": "active"},
    102: {"name": "Omar", "status": "active"}
}

FIELDS = {
    5: {"owner_id": 101, "location": "North Farm"},
    99: {"owner_id": 102, "location": "East Farm"}
}

EQUIPMENT = {
    1: {"type": "tractor", "status": "idle"},          # جاهز
    2: {"type": "harvester", "status": "in_progress"}, # شغال في حقل تاني
    3: {"type": "sprayer", "status": "maintenance"}    # عطلان
}

class DispatchInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    equipment_id: int = Field(description="ID of the equipment to dispatch")
    field_id: int = Field(description="The target field ID")
    
    job_type: Literal["till", "harvest", "chemical_spray"] = Field(
        description="Type of job to perform"
    )
    
    chemical_type: Optional[str] = Field(
        default=None, 
        description="Required only when job_type is chemical_spray"
    )
    
    customer_id: int = Field(description="ID of the authenticated customer")

# The Tool & Logic
@mcp.tool()
async def dispatch_equipment(input_data: DispatchInput) -> str:
    """Dispatch a piece of equipment to perform a job on a specific field."""
    eq_id = input_data.equipment_id
    f_id = input_data.field_id
    job = input_data.job_type
    chem = input_data.chemical_type
    req_by = input_data.customer_id

    # Validation 1
    if job == "chemical_spray" and not chem:
        raise ValueError("chemical_type is required for chemical_spray jobs.")

    # Validation 2
    if req_by not in CUSTOMERS:
        raise ValueError(f"Customer {req_by} not found in database.")

    # Validation 3
    if f_id not in FIELDS:
        raise ValueError(f"Field {f_id} does not exist.")

    # validation 4
    actual_owner = FIELDS[f_id]["owner_id"]
    if actual_owner != req_by:
        raise ValueError(f"SECURITY BLOCK: Field {f_id} does not belong to the requesting customer {req_by}.")

    # Validation 5
    if eq_id not in EQUIPMENT:
        raise ValueError(f"Equipment {eq_id} does not exist.")
    
    # validation 6
    eq_status = EQUIPMENT[eq_id]["status"]
    if eq_status != "idle":
        raise ValueError(f"Equipment {eq_id} cannot be dispatched. Current status is: '{eq_status}'.")

    # --- Success ---
    # TODO: Elicitation Task 5
    
    msg = f"SUCCESS: Equipment {eq_id} dispatched to field {f_id} for {job}."
    if chem:
        msg += f" (Chemical applied: {chem})"
    return msg

if __name__ == "__main__":
    mcp.run(transport='stdio')
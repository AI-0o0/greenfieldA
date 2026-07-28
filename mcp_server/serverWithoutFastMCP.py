# JSON RPC 2
# defines the messages strucutre from/to MCP server
# consist of "name" "description" "inputSchema"
# inputSchema consist from "type" "properities" "required" "additionalProperties" 
# each properities consist of "type" "enum" "description"
{
  "name": "dispatch_equipment",
  "description": "Dispatch a piece of equipment to perform a job on a specific field. Chemical spray jobs require human sign-off before the machine is sent.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "equipment_id": {"type": "integer", "description": "ID of the equipment to dispatch"},
      "field_id": {"type": "integer", "description": "ID of the field the equipment will work on"},
      "job_type": {"type": "string", "enum": ["till", "harvest", "chemical_spray"], "description": "Type of job to perform"},
      "chemical_type": {"type": "string", "description": "Required only when job_type is chemical_spray"},
      "requested_by": {"type": "integer", "description": "ID of the requesting customer's account holder"}
    },
    "required": ["equipment_id", "field_id", "job_type", "requested_by"],
    "additionalProperties": false
  }
}

async def handle_dispatch_equipment(args: dict, session_context) -> dict:
    equipment_id = args["equipment_id"]
    field_id = args["field_id"]
    job_type = args["job_type"]
    chemical_type = args.get("chemical_type")
    requested_by = args["requested_by"]

    # --- Independent validation #1: cross-field consistency the schema can't express ---
    if job_type == "chemical_spray" and not chemical_type:
        return {"error": "chemical_type is required for chemical_spray jobs"}

    # --- Independent validation #2: does the field actually exist, and does it
    #     belong to the customer this user is acting on behalf of? ---
    field = db.get_field(field_id)
    if field is None:
        return {"error": f"field_id {field_id} does not exist"}

    customer = db.get_customer_for_user(requested_by)
    if field.customer_id != customer.customer_id:
        # this is the hallucination/bypass case the issue is written against
        return {"error": "field does not belong to the requesting customer"}

    # --- Independent validation #3: is the equipment actually available? ---
    equipment = db.get_equipment(equipment_id)
    if equipment is None or equipment.status != "idle":
        return {"error": "equipment is not available for dispatch"}

    # ... elicitation branch goes here for job_type == "chemical_spray" (Task 5)

    dispatch = db.create_dispatch(equipment_id, field_id, job_type, chemical_type, requested_by)
    return {"dispatch_id": dispatch.dispatch_id, "status": dispatch.status}
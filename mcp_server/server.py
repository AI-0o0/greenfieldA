from __future__ import annotations

import os
import sys
import asyncio
import jsonschema
from dotenv import load_dotenv

load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import mcp.types as types 
from fastmcp import FastMCP 
from typing import Literal, Optional, List
from mcp.types import ElicitRequestedSchema

from mcp_server.tools import (
    get_db_connection,
    search_agricultural_knowledge,
    process_payment,
    batch_dispatch,
    log_incident_note,
    dispatch_equipment,
)


# Initialize FastMCP server for Greenfield
mcp = FastMCP("Greenfield-Dispatch-Server")


# ============================================
# Tools
# ============================================

mcp.tool()(search_agricultural_knowledge)
mcp.tool()(process_payment)
mcp.tool()(batch_dispatch)
mcp.tool()(log_incident_note)
mcp.tool()(dispatch_equipment)

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

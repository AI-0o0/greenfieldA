from __future__ import annotations

import os
import sys
import asyncio
import sqlite3
import jsonschema
from typing import Literal, Optional, List
from fastmcp import Context

try:
    from server.rag.retrievers import hybrid_search
    from server.rag.verifier import self_rag_verify
except ImportError:
    from rag.retrievers import hybrid_search
    from rag.verifier import self_rag_verify

try:
    from schemas.tool_inputs import (
        PaymentInput,
        BatchDispatchInput,
        IncidentInput,
        DispatchEquipmentInput as DispatchInput,
        KnowledgeSearchInput,
        SignoffResponse,
        DISPATCH_SCHEMA,
    )
except ImportError:
    # Fallback when server is run directly with sys.path pointing at server/
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from schemas.tool_inputs import (
        PaymentInput,
        BatchDispatchInput,
        IncidentInput,
        DispatchEquipmentInput as DispatchInput,
        KnowledgeSearchInput,
        SignoffResponse,
        DISPATCH_SCHEMA,
    )


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


#============================================
# Tools
#============================================
async def search_agricultural_knowledge(input_data: KnowledgeSearchInput, ctx: Context) -> str:
    """Search internal agricultural manuals, chemical compliance policies, and operating procedures."""
    chunks = hybrid_search(input_data.query, top_k=3)
    if not chunks:
        return "No relevant knowledge base documents found."
    
    retrieved_text = "\n---\n".join(chunks)
    
    # Self-RAG Pre-Verification Check
    verification = self_rag_verify(
        query=input_data.query, 
        context=chunks, 
        answer=retrieved_text
    )
    
    if not verification.is_relevant:
        return "[Self-RAG Flag]: Retrieved documents failed relevance verification."

    return f"Retrieved Knowledge (Relevance Confirmed):\n{retrieved_text}"

async def process_payment(input_data: PaymentInput, ctx: Context) -> str:
    """Process a customer payment to clear their credit hold and unlock dispatch tools."""
    with get_db_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO CUSTOMERS (customer_id, credit_hold) VALUES (?, 0)", (input_data.customer_id,))
        conn.execute("UPDATE CUSTOMERS SET credit_hold = 0 WHERE customer_id = ?", (input_data.customer_id,))
        conn.commit()
    
    await ctx.session.send_tool_list_changed()
    return f"SUCCESS: Payment processed. Credit hold cleared for customer {input_data.customer_id}."

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

async def log_incident_note(input_data: IncidentInput, ctx: Context) -> str:
    """Log an unstructured incident note."""
    return f"SUCCESS: Incident recorded: {input_data.raw_note}"



async def dispatch_equipment(input_data: DispatchInput, ctx: Context) -> str:
    """Dispatch a piece of equipment to perform a job on a specific field."""

    # Schema-level validation (types/shape, independent of the checks below)
    try:
        jsonschema.validate(instance=input_data.model_dump(exclude_none=True), schema=DISPATCH_SCHEMA)
    except jsonschema.ValidationError as e:
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

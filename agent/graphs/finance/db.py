"""
agent/graphs/finance/db.py

Database helpers, schema initialization, and persistence queries for the Greenfield
Autonomous Finance Graph using the unified company farm.db SQLite database.
"""

from __future__ import annotations

import os
import json
import sqlite3
import datetime
from typing import Optional, List, Dict, Any


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """
    Returns a SQLite connection to farm.db, ensuring all required core and stateful
    tables exist (Customers, Financing_Applications, Financial_Transactions,
    HITL_Tasks, Tickets, Agent_Tool_Registry).
    """
    db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "db"))
    os.makedirs(db_dir, exist_ok=True)
    target_path = db_path or os.environ.get("GREENFIELD_DB_PATH") or os.path.join(db_dir, "farm.db")
    conn = sqlite3.connect(target_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Ensure foreign key constraints are enabled
    conn.execute("PRAGMA foreign_keys = ON;")

    # Ensure Core Customer & Field Tables
    conn.execute("""
    CREATE TABLE IF NOT EXISTS Customers (
        customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT NOT NULL,
        phone TEXT,
        email TEXT UNIQUE,
        credit_hold BOOLEAN NOT NULL DEFAULT 0
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS Fields (
        field_id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        field_name TEXT NOT NULL,
        location TEXT NOT NULL,
        area REAL NOT NULL,
        FOREIGN KEY (customer_id) REFERENCES Customers(customer_id) ON DELETE CASCADE
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS Equipment (
        equipment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        serial_number TEXT NOT NULL UNIQUE,
        equipment_type TEXT NOT NULL CHECK (equipment_type IN ('tractor', 'sprayer', 'harvester')),
        status TEXT NOT NULL CHECK (status IN ('idle', 'dispatched', 'maintenance', 'offline')),
        current_location TEXT
    )
    """)

    # Ensure Financing Applications & Financial Transactions Tables
    conn.execute("""
    CREATE TABLE IF NOT EXISTS Financing_Applications (
        application_id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        field_id INTEGER,
        requested_amount REAL NOT NULL,
        purpose TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending_eligibility'
            CHECK (status IN ('pending_eligibility', 'pending_documents', 'under_review', 'submitted', 'approved', 'rejected', 'disbursed', 'cancelled')),
        admin_approved_by INTEGER,
        provider_reference TEXT,
        interest_rate REAL,
        term_months INTEGER,
        monthly_payment REAL,
        farmer_accepted BOOLEAN,
        rejection_reason TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id) REFERENCES Customers(customer_id) ON DELETE CASCADE,
        FOREIGN KEY (field_id) REFERENCES Fields(field_id) ON DELETE SET NULL
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS Financial_Transactions (
        transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id INTEGER NOT NULL,
        customer_id INTEGER NOT NULL,
        transaction_type TEXT NOT NULL CHECK (transaction_type IN ('disbursement', 'repayment', 'fee', 'adjustment')),
        amount REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('pending', 'completed', 'failed', 'reverted')),
        verification_hash TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (application_id) REFERENCES Financing_Applications(application_id) ON DELETE CASCADE,
        FOREIGN KEY (customer_id) REFERENCES Customers(customer_id) ON DELETE CASCADE
    )
    """)

    # Ensure HITL Tasks Table for explicit human-in-the-loop escalations
    conn.execute("""
    CREATE TABLE IF NOT EXISTS HITL_Tasks (
        task_id INTEGER PRIMARY KEY AUTOINCREMENT,
        thread_id TEXT NOT NULL,
        application_id INTEGER,
        node_name TEXT NOT NULL,
        reason TEXT NOT NULL,
        assessed_amount REAL,
        dscr REAL,
        risk_level TEXT,
        state_snapshot TEXT,
        status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'more_info')),
        admin_notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        resolved_at DATETIME,
        FOREIGN KEY (application_id) REFERENCES Financing_Applications(application_id) ON DELETE SET NULL
    )
    """)

    # Ensure Tickets Table for unplanned mid-node failures
    conn.execute("""
    CREATE TABLE IF NOT EXISTS Tickets (
        ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
        thread_id TEXT NOT NULL,
        failed_node TEXT NOT NULL,
        error_type TEXT NOT NULL,
        error_message TEXT NOT NULL,
        state_snapshot TEXT,
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'resolved')),
        resolution_notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        resolved_at DATETIME
    )
    """)

    # Ensure Agent Tool Registry for runtime tool add/remove management
    conn.execute("""
    CREATE TABLE IF NOT EXISTS Agent_Tool_Registry (
        agent_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        is_enabled BOOLEAN NOT NULL DEFAULT 1,
        description TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (agent_id, tool_name)
    )
    """)

    conn.commit()
    return conn


def serialize_state_for_db(state: Dict[str, Any]) -> str:
    """Safely converts state dictionary into a clean JSON string for database storage."""
    def _default(obj: Any) -> Any:
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        if isinstance(obj, set):
            return list(obj)
        return str(obj)
    return json.dumps(state, default=_default, indent=2)


def fetch_farmer_db_profile(customer_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches farmer profile, associated fields, total acreage, active credit hold status,
    and assigned equipment from the shared farm.db.
    """
    with get_db_connection(db_path) as conn:
        customer = conn.execute(
            "SELECT * FROM Customers WHERE customer_id = ?", (customer_id,)
        ).fetchone()
        if not customer:
            return {}

        fields = conn.execute(
            "SELECT * FROM Fields WHERE customer_id = ?", (customer_id,)
        ).fetchall()

        total_area = sum(f["area"] for f in fields) if fields else 0.0

        # Check active equipment deployed on customer fields
        equipment_rows = conn.execute(
            """SELECT e.* FROM Equipment e 
               JOIN Dispatch_Jobs dj ON e.equipment_id = dj.equipment_id 
               JOIN Fields f ON dj.field_id = f.field_id 
               WHERE f.customer_id = ?""",
            (customer_id,),
        ).fetchall()

        return {
            "customer_id": customer["customer_id"],
            "company_name": customer["company_name"],
            "credit_hold": bool(customer["credit_hold"]),
            "phone": customer["phone"] if "phone" in customer.keys() else None,
            "email": customer["email"] if "email" in customer.keys() else None,
            "total_area": total_area,
            "fields": [dict(f) for f in fields],
            "active_equipment": [dict(e) for e in equipment_rows],
        }

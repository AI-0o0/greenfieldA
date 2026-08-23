"""
agents/graphs/finance/checkpointer.py

Persistent SQLite checkpointer factory for durable state graphs.
Ensures state is persisted to disk after every node transition and enables
crash-and-resume across process restarts.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Optional
from langgraph.checkpoint.sqlite import SqliteSaver


def get_sqlite_checkpointer(db_path: Optional[str] = None) -> SqliteSaver:
    """
    Creates and returns a persistent SqliteSaver checkpointer for durable state
    persistence across process restarts.
    """
    db_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "db"))
    os.makedirs(db_dir, exist_ok=True)
    target_path = db_path or os.environ.get("GREENFIELD_CHECKPOINT_DB") or os.path.join(db_dir, "checkpoints.sqlite")
    conn = sqlite3.connect(target_path, check_same_thread=False)
    return SqliteSaver(conn)

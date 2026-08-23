from __future__ import annotations

import operator
from typing import Optional, TypedDict, List, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class CaseState(TypedDict):
    # ------------------------------------------------------------
    # Identity & persistence
    # ------------------------------------------------------------
    case_id: int                    
    thread_id: str                  
    status: str                     

    # ------------------------------------------------------------
    # Conversation (CRITICAL FIX: Added add_messages reducer)
    # ------------------------------------------------------------
    messages: Annotated[List[BaseMessage], add_messages]

    # ------------------------------------------------------------
    # Ownership (FKs into existing Customers / Fields tables)
    # ------------------------------------------------------------
    customer_id: int
    field_id: int

    # ------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------
    rag_context: str                
    memory_context: str             

    # ------------------------------------------------------------
    # Case data (each stored as JSON text in Crop_Cases, dict in-graph)
    # ------------------------------------------------------------
    crop_data: dict
    diagnosis: dict
    proposed_treatment: dict        

    # ------------------------------------------------------------
    # Dispatch linkage (set once execute_treatment succeeds)
    # ------------------------------------------------------------
    dispatch_id: Optional[int]      

    # ------------------------------------------------------------
    # Farmer confirmation / observation
    # ------------------------------------------------------------
    farmer_confirmed: Optional[bool]
    observation_result: Optional[dict]   
    
    # ------------------------------------------------------------
    # Retry Counter (CRITICAL FIX: Added operator.add reducer)
    # ------------------------------------------------------------
    retry_count: int

    # ------------------------------------------------------------
    # HITL (Crop_HITL_Tasks)
    # ------------------------------------------------------------
    hitl_required: bool
    hitl_status: Optional[str]      
    hitl_task_id: Optional[int]     

    # ------------------------------------------------------------
    # Failure ticket (shared Tickets table)
    # ------------------------------------------------------------
    ticket_id: Optional[int]        
    ticket_status: Optional[str]
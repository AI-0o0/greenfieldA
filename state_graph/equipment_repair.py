import os
import sqlite3
from typing import TypedDict, Annotated, List, Optional
from typing_extensions import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt

# 1. Define the state schema for equipment maintenance workflow
class EquipmentRepairState(TypedDict):
    equipment_id: str
    issue_description: str
    diagnosis_steps: List[str]  # Task Decomposition output
    manual_context: str        # RAG output
    repair_cost: float
    parts_needed: List[str]
    hitl_approved: Optional[bool]
    parts_order_status: Optional[str]
    failure_ticket_id: Optional[str]
    status: str

# 2. Node 1: RAG & Task Decomposition
def node_diagnose_and_rag(state: EquipmentRepairState) -> dict:
    print("\n--- [Node 1] RAG & Task Decomposition ---")
    
    # Retrieve technical manual via RAG pattern
    manual_info = f"Manual Entry for {state['equipment_id']}: Check fuel line and replace filter for dark smoke."
    
    # Decompose the maintenance process into concrete steps
    steps = [
        "1. Inspect fuel injection nozzle.",
        "2. Replace air & fuel filters.",
        "3. Recalibrate pump pressure."
    ]
    
    # Calculate repair cost (In production, this is dynamically fetched from DB via MCP tool)
    estimated_cost = 650.0  
    
    return {
        "manual_context": manual_info,
        "diagnosis_steps": steps,
        "repair_cost": estimated_cost,
        "parts_needed": ["Fuel Filter XL", "Injector Nozzle"],
        "status": "diagnosed"
    }

# 3. Node 2: Cost Policy Evaluation
def node_check_cost_policy(state: EquipmentRepairState) -> dict:
    print("\n--- [Node 2] Checking Cost Policy ---")
    return {"status": "cost_evaluated"}

# Conditional routing based on the $500 threshold policy
def route_after_cost_check(state: EquipmentRepairState) -> Literal["node_hitl_approval", "node_order_parts_api"]:
    if state["repair_cost"] > 500.0:
        return "node_hitl_approval"
    return "node_order_parts_api"

# 4. Node 3: Explicit Human-In-The-Loop (HITL) Pause
def node_hitl_approval(state: EquipmentRepairState) -> dict:
    print(f"\n--- [Node 3 - HITL] Cost (${state['repair_cost']}) exceeds $500! Pausing for Admin approval... ---")
    
    # Explicit graph pause, surfacing data to the platform UI
    admin_response = interrupt({
        "type": "HITL_APPROVAL_REQUIRED",
        "reason": f"Repair cost ${state['repair_cost']} exceeds policy limit of $500.",
        "equipment_id": state["equipment_id"],
        "parts": state["parts_needed"]
    })
    
    # Capture human admin decision upon execution resume
    approved = admin_response.get("approved", False)
    return {
        "hitl_approved": approved,
        "status": "approved" if approved else "rejected_by_admin"
    }

def route_after_hitl(state: EquipmentRepairState) -> Literal["node_order_parts_api", "__end__"]:
    if state.get("hitl_approved"):
        return "node_order_parts_api"
    print("\n[Terminated] Repair rejected by Admin.")
    return END

# 5. Node 4: Supplier API Integration & Failure Ticket Handling
def node_order_parts_api(state: EquipmentRepairState) -> dict:
    print("\n--- [Node 4] Calling Supplier API for Parts Order ---")
    
    try:
        # Flag to simulate an unexpected external API failure or Schema error
        simulate_api_failure = False 
        
        if simulate_api_failure:
            raise RuntimeError("503 Supplier API Unavailable or Schema Mismatch")
            
        return {
            "parts_order_status": "ORDERED_AWAITING_DELIVERY",
            "status": "awaiting_parts_delivery"
        }
    except Exception as e:
        # Create an unplanned failure ticket surfaced on the platform UI
        ticket_id = f"TICKET-{state['equipment_id']}-889"
        print(f"\n[FAILURE TICKET CREATED] {ticket_id}: {str(e)}")
        
        return {
            "failure_ticket_id": ticket_id,
            "status": "ticket_opened"
        }

# Construct the State Graph topology
builder = StateGraph(EquipmentRepairState)

builder.add_node("node_diagnose_and_rag", node_diagnose_and_rag)
builder.add_node("node_check_cost_policy", node_check_cost_policy)
builder.add_node("node_hitl_approval", node_hitl_approval)
builder.add_node("node_order_parts_api", node_order_parts_api)

builder.add_edge(START, "node_diagnose_and_rag")
builder.add_edge("node_diagnose_and_rag", "node_check_cost_policy")

builder.add_conditional_edges("node_check_cost_policy", route_after_cost_check)
builder.add_conditional_edges("node_hitl_approval", route_after_hitl)
builder.add_edge("node_order_parts_api", END)

# Set up SQLite checkpointer for durable state retention across restarts
conn = sqlite3.connect("checkpoints.db", check_same_thread=False)
memory = SqliteSaver(conn)

# Compile graph with persistence checkpointer
equipment_repair_app = builder.compile(checkpointer=memory)
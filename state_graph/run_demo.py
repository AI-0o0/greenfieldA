from equipment_repair import equipment_repair_app
from langgraph.types import Command

# 1. Setup execution thread configuration to track state checkpoints in the DB
config = {"configurable": {"thread_id": "repair_tractor_99"}}

# Initial input payload passed from the user interface at thread start
initial_input = {
    "equipment_id": "TRACTOR-CAT-01",
    "issue_description": "Engine output low and emitting black smoke."
}

print("=== Starting Repair Graph Execution ===")

# Initial execution: The graph automatically pauses at the HITL node as repair_cost > $500
for event in equipment_repair_app.stream(initial_input, config=config):
    print(event)

# 2. Simulate administrative approval received from the Platform UI to resume workflow
print("\n=== Simulating Admin Approval via Platform UI ===")

# Command to resume execution from the persistent checkpoint
resume_command = Command(resume={"approved": True})

# Resume execution from the stored checkpoint state without re-running earlier nodes
for event in equipment_repair_app.stream(resume_command, config=config):
    print(event)
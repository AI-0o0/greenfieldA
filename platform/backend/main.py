from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from langgraph.types import Command

# Import compiled LangGraph app from state_graph module
from state_graph.equipment_repair import equipment_repair_app

app = FastAPI(title="Greenfield Agricultural Agency Platform")

# تحديد المسار الصحيح للـ Frontend بمرونة بصرف النظر عن موقع تشغيل uvicorn
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"


# Pydantic Schemas for Chat & HITL Approvals
class ChatRequest(BaseModel):
    message: str
    agent: str


class ChatResponse(BaseModel):
    reply: str


class ApprovalRequest(BaseModel):
    thread_id: str
    approved: bool


# Serve Static Frontend
@app.get("/")
async def serve_frontend():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail=f"Index file not found at: {index_file}")
    return FileResponse(index_file)


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    return ChatResponse(reply=f"You sent: {request.message}")


# Endpoint to handle HITL approval/rejection from Admin UI
@app.post("/api/equipment-repair/approve")
async def approve_repair_task(payload: ApprovalRequest):
    """Resume execution of a paused equipment repair workflow following Admin approval."""
    config = {"configurable": {"thread_id": payload.thread_id}}
    
    try:
        # Update state with defaults if running directly
        equipment_repair_app.update_state(
            config, 
            {
                "equipment_id": "PART-001",
                "issue_description": "Fuel Filter Replacement needed",
                "approved": payload.approved
            }
        )
        
        # Resume paused LangGraph execution via Command
        resume_command = Command(resume={"approved": payload.approved})
        result_events = []
        
        for event in equipment_repair_app.stream(resume_command, config=config):
            result_events.append(str(event))
            
        return {
            "status": "success",
            "message": f"Execution resumed for thread {payload.thread_id}",
            "events": result_events
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
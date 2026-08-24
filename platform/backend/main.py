from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from langgraph.types import Command

from state_graph.equipment_repair import equipment_repair_app
from rag.retrievers import hybrid_search

app = FastAPI(title="Greenfield Agricultural Agency Platform")

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"


class ChatRequest(BaseModel):
    message: str
    agent: str


class ChatResponse(BaseModel):
    reply: str


class ApprovalRequest(BaseModel):
    thread_id: str
    approved: bool


@app.get("/")
async def serve_frontend():
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail=f"Index file not found at: {index_file}")
    return FileResponse(index_file)


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        if request.agent == "Memory/RAG Agent":
            # Search equipment knowledge base using RAG hybrid search
            rag_results = hybrid_search(request.message)
            
            if rag_results:
                # معالجة الناتج سواء كان Document object أو str عادي
                extracted_texts = []
                for doc in rag_results:
                    if hasattr(doc, "page_content"):
                        extracted_texts.append(doc.page_content)
                    elif isinstance(doc, str):
                        extracted_texts.append(doc)
                    else:
                        extracted_texts.append(str(doc))

                context_str = "\n\n".join(extracted_texts)
                return ChatResponse(reply=f"Based on Equipment Maintenance Manuals:\n\n{context_str}")
            else:
                return ChatResponse(reply="No relevant maintenance procedures found.")
        else:
            return ChatResponse(reply=f"[{request.agent}] Received issue: '{request.message}'")
    except Exception as e:
        return ChatResponse(reply=f"Error processing request: {str(e)}")


@app.post("/api/equipment-repair/approve")
async def approve_repair_task(payload: ApprovalRequest):
    config = {"configurable": {"thread_id": payload.thread_id}}
    try:
        equipment_repair_app.update_state(
            config, 
            {
                "equipment_id": "PART-001",
                "issue_description": "Fuel Filter Replacement needed",
                "approved": payload.approved
            }
        )
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
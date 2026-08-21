from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="Greenfield Agricultural Agency Platform Smoke Test")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


class ChatRequest(BaseModel):
    message: str
    agent: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/")
async def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    return ChatResponse(reply=f"You sent: {request.message}")

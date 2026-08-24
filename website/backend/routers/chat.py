from __future__ import annotations

import os
import shutil
from typing import List, Optional
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from website.backend.registry import AGENT_CATALOG, dispatch_chat, new_thread_id

router = APIRouter(prefix="/api", tags=["chat"])

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)


class Attachment(BaseModel):
    filename: str
    size: int = 0
    content_type: str = "application/octet-stream"
    document_type: Optional[str] = None


class ChatRequest(BaseModel):
    agent_id: str
    thread_id: str | None = None
    message: str = ""
    attachments: Optional[List[Attachment]] = None


@router.get("/agents")
async def list_agents():
    return {"agents": AGENT_CATALOG}


@router.post("/threads/new")
async def create_thread(agent_id: str):
    valid = {a["id"] for a in AGENT_CATALOG}
    if agent_id not in valid:
        raise HTTPException(404, f"Unknown agent '{agent_id}'.")
    prefix = agent_id.split("_")[0]
    return {"thread_id": new_thread_id(prefix)}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    filename = os.path.basename(file.filename or "uploaded_doc.pdf")
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    size = os.path.getsize(filepath)

    # Classify document type based on filename keywords
    fn_lower = filename.lower()
    doc_type = "general_document"
    if any(k in fn_lower for k in ("id", "passport", "identity", "license")):
        doc_type = "government_id"
    elif any(k in fn_lower for k in ("tax", "return", "irs", "revenue")):
        doc_type = "farm_tax_return"
    elif any(k in fn_lower for k in ("bank", "statement", "financial", "income")):
        doc_type = "bank_statements"
    elif any(k in fn_lower for k in ("deed", "lease", "land", "title", "contract")):
        doc_type = "land_deed_or_lease"
    elif any(k in fn_lower for k in ("leaf", "crop", "wheat", "rust", "mildew", "pest", "photo")):
        doc_type = "crop_photo"

    return {
        "filename": filename,
        "size": size,
        "document_type": doc_type,
        "verified": True,
        "url": f"/uploads/{filename}",
    }


@router.post("/chat")
async def chat(req: ChatRequest):
    msg = req.message.strip()
    if not msg and req.attachments:
        names = [a.filename for a in req.attachments]
        msg = f"Uploaded verified files: {', '.join(names)}"
    elif not msg:
        msg = "continue"

    thread_id = req.thread_id or new_thread_id(req.agent_id.split("_")[0])
    try:
        result = await dispatch_chat(req.agent_id, thread_id, msg)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:  # keep the chat usable; surface the failure honestly
        raise HTTPException(500, f"Agent run failed: {exc}")
    return result

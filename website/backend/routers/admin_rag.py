"""
website/backend/routers/admin_rag.py

Admin surface: add and remove documents from the RAG store used by the
Memory/RAG agent. Mutations hit the SAME live Chroma collection the
retrievers query, so the very next retrieval reflects the change.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from rag.vector_store import add_document, delete_document, list_documents

router = APIRouter(prefix="/api/admin/documents", tags=["admin-rag"])


class DocumentIn(BaseModel):
    source_name: str
    text: str


@router.get("")
async def get_documents():
    return {"documents": await asyncio.to_thread(list_documents)}


@router.post("")
async def upload_document(doc: DocumentIn):
    if not doc.source_name.strip() or not doc.text.strip():
        raise HTTPException(400, "source_name and text are required.")
    result = await asyncio.to_thread(add_document, doc.source_name.strip(), doc.text)
    return {"status": "added", **result}


@router.delete("/{source_name:path}")
async def remove_document(source_name: str):
    removed = await asyncio.to_thread(delete_document, source_name)
    if removed == 0:
        raise HTTPException(404, f"No document '{source_name}' in the vector store.")
    return {"status": "deleted", "source": source_name, "chunks_removed": removed}

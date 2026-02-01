"""
Upload route handlers for FIR PDF processing.
"""

import json
from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Request
from fastapi.responses import JSONResponse
from typing import Optional

from app.langgraph.workflow import graph
from .config import results_store
from .session import get_session_id

router = APIRouter()


@router.post("/upload")
async def upload_pdf(
    request: Request,
    file: Optional[UploadFile] = File(None),
    sections: Optional[str] = Form(None)
):
    """Upload PDF or add sections to existing workflow."""
    
    workflow_id = get_session_id(request)
    
    # Parse sections
    try:
        sections_list = json.loads(sections) if sections else []
    except json.JSONDecodeError:
        sections_list = []
    
    # New workflow - require file
    if not file:
        if workflow_id not in results_store:
            raise HTTPException(status_code=400, detail="PDF file required")
    else:
        # Validate file
        if not file.filename or not file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files allowed")
        try:
            file_bytes = await file.read()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")
    
    # Prepare state
    graph_state = {"sections": sections_list}
    if file:
        graph_state["pdf_bytes"] = file_bytes
        graph_state["pdf_filename"] = file.filename or "document.pdf"
    
    # Invoke graph (checkpoint loads previous state if continuing)
    result = graph.invoke(
        graph_state,
        config={"configurable": {"thread_id": workflow_id}}
    )
    
    # Store result (drop pdf_bytes)
    result.pop("pdf_bytes", None)
    result["workflow_id"] = workflow_id
    results_store[workflow_id] = result
    
    return JSONResponse({
        "success": True,
        "workflow_id": workflow_id,
        "redirect_url": f"/results/{workflow_id}",
    })
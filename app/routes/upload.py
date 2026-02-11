"""
Upload route handlers for FIR PDF processing.
"""

import json
import logging
from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Request
from fastapi.responses import JSONResponse
from typing import Optional

from app.langgraph.workflow import graph
from .config import results_store
from .session import get_session_id

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/upload")
async def upload_pdf(
    request: Request,
    file: Optional[UploadFile] = File(None),
    sections: Optional[str] = Form(None)
):
    """Upload PDF or add sections to existing workflow."""
    
    workflow_id = get_session_id(request)
    logger.info(f"📥 Starting upload request for workflow_id: {workflow_id}")
    
    # Parse sections
    try:
        sections_list = json.loads(sections) if sections else []
    except json.JSONDecodeError:
        sections_list = []
    
    logger.info(f"📋 Selected sections: {sections_list}")
    
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
            logger.info(f"📄 PDF file received: {file.filename}, size: {len(file_bytes)} bytes")
        except Exception as e:
            logger.error(f"❌ Error reading file: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")
    
    # Prepare state
    graph_state = {"sections": sections_list}
    if file:
        graph_state["pdf_bytes"] = file_bytes
        graph_state["pdf_filename"] = file.filename or "document.pdf"
    
    # Stream graph execution to see real-time progress
    logger.info("🚀 Starting LangGraph execution...")
    config = {"configurable": {"thread_id": workflow_id}}
    result = None
    
    try:
        # Use stream to get real-time updates and log progress
        # The stream executes the graph and yields events as each node completes
        import sys
        for event in graph.stream(graph_state, config=config):
            # Log each node execution as it completes
            for node_name, node_output in event.items():
                logger.info(f"✅ Node completed: {node_name}")
                sys.stdout.flush()  # Force flush to see logs immediately
                if isinstance(node_output, dict):
                    # Log what was added to state
                    keys_added = [k for k in node_output.keys() if k != "pdf_bytes"]
                    if keys_added:
                        logger.debug(f"   State updated with keys: {keys_added}")
                        sys.stdout.flush()
        
        # After streaming completes, get the final state from checkpointer
        # The stream already executed everything, so we just need the final state
        final_state = graph.get_state(config)
        if final_state and final_state.values:
            result = final_state.values
        else:
            # Fallback: if state not available, invoke to get final result
            logger.warning("⚠️ Could not get state from checkpointer, invoking graph to get final result")
            sys.stdout.flush()
            result = graph.invoke(graph_state, config=config)
        
        logger.info("✅ LangGraph execution completed successfully")
        sys.stdout.flush()
        
    except Exception as e:
        logger.error(f"❌ Error during LangGraph execution: {str(e)}", exc_info=True)
        sys.stdout.flush()
        raise HTTPException(status_code=500, detail=f"Error processing workflow: {str(e)}")
    
    # Store result (drop pdf_bytes)
    result.pop("pdf_bytes", None)
    result["workflow_id"] = workflow_id
    results_store[workflow_id] = result
    
    logger.info(f"✅ Workflow completed for workflow_id: {workflow_id}")
    
    return JSONResponse({
        "success": True,
        "workflow_id": workflow_id,
        "redirect_url": f"/results/{workflow_id}",
    })
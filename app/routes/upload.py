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
    
    config = {"configurable": {"thread_id": workflow_id}}
    
    # ✅ KEY FIX: Load prior state from checkpoint FIRST
    prior_state = graph.get_state(config)
    if prior_state and prior_state.values:
        graph_state = dict(prior_state.values)  # Start with prior results
        logger.info(f"✅ Loaded prior state with keys: {list(graph_state.keys())}")
    else:
        graph_state = {}  # New workflow
    
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
            graph_state["pdf_bytes"] = file_bytes
            graph_state["pdf_filename"] = file.filename or "document.pdf"
        except Exception as e:
            logger.error(f"❌ Error reading file: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")
    
    # ✅ Update sections (merge with prior if they exist)
    prior_sections = graph_state.get("sections", [])
    graph_state["sections"] = list(set(prior_sections + sections_list))  # Deduplicate
    logger.info(f"📋 Running with sections: {graph_state['sections']}")
    
    # Stream graph execution
    logger.info("🚀 Starting LangGraph execution...")
    result = None
    
    try:
        import sys
        for event in graph.stream(graph_state, config=config):
            for node_name, node_output in event.items():
                logger.info(f"✅ Node completed: {node_name}")
                sys.stdout.flush()
                if isinstance(node_output, dict):
                    keys_added = [k for k in node_output.keys() if k != "pdf_bytes"]
                    if keys_added:
                        logger.debug(f"   State updated with keys: {keys_added}")
                        sys.stdout.flush()
        
        # Get final state
        final_state = graph.get_state(config)
        if final_state and final_state.values:
            result = final_state.values
        else:
            logger.warning("⚠️ Could not get state from checkpointer")
            sys.stdout.flush()
            result = graph.invoke(graph_state, config=config)
        
        logger.info("✅ LangGraph execution completed successfully")
        sys.stdout.flush()
        
    except Exception as e:
        logger.error(f"❌ Error during LangGraph execution: {str(e)}", exc_info=True)
        sys.stdout.flush()
        raise HTTPException(status_code=500, detail=f"Error processing workflow: {str(e)}")
    
    # Store result
    result.pop("pdf_bytes", None)
    result["workflow_id"] = workflow_id
    results_store[workflow_id] = result
    
    logger.info(f"✅ Workflow completed for workflow_id: {workflow_id}")
    
    return JSONResponse({
        "success": True,
        "workflow_id": workflow_id,
        "redirect_url": f"/results/{workflow_id}",
    })
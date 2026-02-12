"""
Upload route handlers for FIR PDF processing.
"""

import json
import logging
import uuid
import time
import threading
from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Optional

from app.langgraph.workflow import graph
from .config import results_store, job_store
from .session import get_session_id

logger = logging.getLogger(__name__)

router = APIRouter()


def process_workflow_background(
    job_id: str,
    workflow_id: str,
    file_bytes: Optional[bytes],
    filename: Optional[str],
    sections_list: list,
    is_new_workflow: bool
):
    """
    Background task to process the workflow asynchronously.
    This runs independently of the HTTP request.
    """
    import sys
    
    try:
        # Update job status
        job_store[job_id]["status"] = "processing"
        job_store[job_id]["progress"] = 5
        job_store[job_id]["updated_at"] = time.time()
        
        config = {"configurable": {"thread_id": workflow_id}}
        
        # Load prior state if continuing workflow
        graph_state = {}
        if not is_new_workflow:
            prior_state = graph.get_state(config)
            if prior_state and prior_state.values:
                graph_state = dict(prior_state.values)
                logger.info(f"✅ Loaded prior state with keys: {list(graph_state.keys())}")
                job_store[job_id]["progress"] = 10
        
        # Set up graph state
        if is_new_workflow:
            if file_bytes:
                graph_state["pdf_bytes"] = file_bytes
                graph_state["pdf_filename"] = filename or "document.pdf"
            graph_state["sections"] = sections_list
        else:
            # Merge sections
            prior_sections = graph_state.get("sections", [])
            graph_state["sections"] = list(set(prior_sections + sections_list))
        
        logger.info(f"🚀 Starting background workflow processing for job_id: {job_id}, workflow_id: {workflow_id}")
        logger.info(f"📊 Graph state keys: {list(graph_state.keys())}")
        logger.info(f"📋 Sections to process: {graph_state.get('sections', [])}")
        
        # Validate sections
        sections_list = graph_state.get("sections", [])
        if not sections_list:
            raise ValueError("No sections selected for processing")
        
        # Update progress after setup
        job_store[job_id]["progress"] = 10
        job_store[job_id]["updated_at"] = time.time()
        logger.info(f"📈 Progress updated to 10% - Starting graph execution")
        sys.stdout.flush()
        
        # Track total nodes to estimate progress
        total_nodes = len(sections_list) + 2  # +2 for read_pdf and extract_fir_fact
        logger.info(f"📊 Total nodes expected: {total_nodes}")
        completed_nodes = 0
        
        # Stream graph execution and update progress
        result = None
        event_count = 0
        logger.info(f"🔄 Starting graph.stream()...")
        sys.stdout.flush()
        
        try:
            for event in graph.stream(graph_state, config=config):
                event_count += 1
                logger.info(f"📦 Received event #{event_count}: {list(event.keys())}")
                sys.stdout.flush()
                
                for node_name, node_output in event.items():
                    completed_nodes += 1
                    progress = min(10 + int((completed_nodes / max(total_nodes, 1)) * 85), 95)
                    job_store[job_id]["progress"] = progress
                    job_store[job_id]["updated_at"] = time.time()
                    
                    logger.info(f"✅ Node completed: {node_name} (Progress: {progress}%, Completed: {completed_nodes}/{total_nodes})")
                    sys.stdout.flush()
            
            if event_count == 0:
                logger.warning("⚠️ No events received from graph.stream() - graph may not have executed")
                sys.stdout.flush()
        except Exception as stream_error:
            logger.error(f"❌ Error during graph.stream(): {str(stream_error)}", exc_info=True)
            sys.stdout.flush()
            raise
        
        # Get final state
        final_state = graph.get_state(config)
        if final_state and final_state.values:
            result = final_state.values
        else:
            logger.warning("⚠️ Could not get state from checkpointer")
            result = graph.invoke(graph_state, config=config)
        
        # Store result
        result.pop("pdf_bytes", None)
        result["workflow_id"] = workflow_id
        results_store[workflow_id] = result
        
        # Update job status to completed
        job_store[job_id]["status"] = "completed"
        job_store[job_id]["workflow_id"] = workflow_id
        job_store[job_id]["progress"] = 100
        job_store[job_id]["updated_at"] = time.time()
        
        logger.info(f"✅ Background workflow completed for job_id: {job_id}, workflow_id: {workflow_id}")
        sys.stdout.flush()
        
    except Exception as e:
        logger.error(f"❌ Error in background workflow processing for job_id: {job_id}: {str(e)}", exc_info=True)
        sys.stdout.flush()
        
        # Update job status to failed
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error"] = str(e)
        job_store[job_id]["updated_at"] = time.time()


@router.post("/upload")
async def upload_pdf(
    request: Request,
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    sections: Optional[str] = Form(None)
):
    """
    Upload PDF or add sections to existing workflow.
    Returns immediately with a job_id for status polling.
    """
    
    workflow_id = get_session_id(request)
    logger.info(f"📥 Starting upload request for workflow_id: {workflow_id}")
    
    # Parse sections
    try:
        sections_list = json.loads(sections) if sections else []
    except json.JSONDecodeError:
        sections_list = []
    
    logger.info(f"📋 Selected sections: {sections_list}")
    
    # Validate sections
    if not sections_list:
        raise HTTPException(status_code=400, detail="At least one section must be selected for analysis")
    
    # Generate unique job_id
    job_id = str(uuid.uuid4())
    
    # Check if this is a new workflow or continuing an existing one
    config = {"configurable": {"thread_id": workflow_id}}
    prior_state = graph.get_state(config)
    is_new_workflow = not prior_state or not prior_state.values
    
    # Validate file if new workflow
    file_bytes = None
    filename = None
    if is_new_workflow:
        if not file:
            raise HTTPException(status_code=400, detail="PDF file required for new workflow")
        
        if not file.filename or not file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files allowed")
        
        try:
            file_bytes = await file.read()
            filename = file.filename or "document.pdf"
            logger.info(f"📄 PDF file received: {filename}, size: {len(file_bytes)} bytes")
        except Exception as e:
            logger.error(f"❌ Error reading file: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")
    
    # Initialize job in job_store
    job_store[job_id] = {
        "status": "processing",
        "workflow_id": None,
        "progress": 0,
        "error": None,
        "created_at": time.time(),
        "updated_at": time.time()
    }
    
    # Start background task
    background_tasks.add_task(
        process_workflow_background,
        job_id,
        workflow_id,
        file_bytes,
        filename,
        sections_list,
        is_new_workflow
    )
    
    logger.info(f"✅ Job {job_id} created and background task started for workflow_id: {workflow_id}")
    
    # Return immediately with job_id
    return JSONResponse({
        "success": True,
        "job_id": job_id,
        "status": "processing",
        "message": "Workflow processing started. Poll /status/{job_id} for progress."
    })


@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Get the status of an asynchronous job.
    Frontend should poll this endpoint every 2-3 seconds.
    """
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = job_store[job_id]
    
    response = {
        "job_id": job_id,
        "status": job["status"],
        "progress": job["progress"],
        "updated_at": job["updated_at"]
    }
    
    if job["status"] == "completed":
        response["workflow_id"] = job["workflow_id"]
        response["redirect_url"] = f"/results/{job['workflow_id']}"
    elif job["status"] == "failed":
        response["error"] = job["error"]
    
    return JSONResponse(response)

"""
Document generation route handlers.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from .config import results_store
from ..utils.document_generator import generate_document
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/document/{workflow_id}")
async def generate_document_endpoint(workflow_id: str):
    """
    Generate and download a Word document for the workflow.
    
    Args:
        workflow_id: Unique workflow identifier
        
    Returns:
        Word document file download
        
    Raises:
        HTTPException: If workflow not found or generation fails
    """
    if workflow_id not in results_store:
        raise HTTPException(status_code=404, detail="Workflow result not found")
    
    try:
        workflow_state = results_store[workflow_id]
        document_bytes = generate_document(workflow_state)
        
        # Generate filename
        filename = f"FIR_Report_{workflow_id}.docx"
        
        return Response(
            content=document_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        logger.error(f"Error generating document for workflow {workflow_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating document: {str(e)}")

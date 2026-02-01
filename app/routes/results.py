"""
Results route handlers for displaying analysis results.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .config import results_store, TEMPLATES_DIR
from .utils import format_state_for_display

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def load_result(workflow_id: str) -> dict:
    """Load result from in-memory store only (no file I/O)."""
    if workflow_id in results_store:
        return results_store[workflow_id]
    raise HTTPException(status_code=404, detail="Workflow result not found")


# Removed - React app handles the results page now


@router.get("/api/results/{workflow_id}")
async def get_results_api(workflow_id: str):
    """
    Get results as JSON (API endpoint).
    
    Args:
        workflow_id: Unique workflow identifier
        
    Returns:
        JSON response with formatted workflow result
        
    Raises:
        HTTPException: If result not found
    """
    result = load_result(workflow_id)
    # Format the result for the React app
    from .utils import format_state_for_display
    return format_state_for_display(result)

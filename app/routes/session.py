"""
Session management utilities.
"""

import uuid
from fastapi import Request, APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


def get_session_id(request: Request) -> str:
    """
    Get or create session ID from request session.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Session ID (existing or newly created)
    """
    session = request.session
    
    if "session_id" in session:
        return session["session_id"]
    else:
        session["session_id"] = str(uuid.uuid4())
        return session["session_id"]


def create_new_session(request: Request) -> str:
    """
    Force create a new session ID, clearing any existing session.
    This should be called when a user logs in to ensure a fresh session.
    
    Args:
        request: FastAPI request object
        
    Returns:
        New session ID
    """
    session = request.session
    # Clear existing session data
    session.clear()
    # Create new session ID
    new_session_id = str(uuid.uuid4())
    session["session_id"] = new_session_id
    return new_session_id


@router.post("/login")
async def login_endpoint(request: Request):
    """
    Login endpoint that creates a fresh session for the user.
    This ensures each login gets a new session ID, preventing
    workflow data from previous sessions from being mixed.
    """
    new_session_id = create_new_session(request)
    return JSONResponse({
        "success": True,
        "session_id": new_session_id,
        "message": "New session created"
    })

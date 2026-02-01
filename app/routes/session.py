"""
Session management utilities.
"""

import uuid
from fastapi import Request


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

"""
Routes module for FIR Legal Analysis API.
"""

from fastapi import APIRouter
from .upload import router as upload_router
from .results import router as results_router
from .document import router as document_router

# Create main router
api_router = APIRouter()

# Include sub-routers
api_router.include_router(upload_router, tags=["upload"])
api_router.include_router(results_router, tags=["results"])
api_router.include_router(document_router, tags=["document"])
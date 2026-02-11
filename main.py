"""
Main entry point for FIR Legal Analysis API application.
"""

import sys
import io
import logging
import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path

# Fix Windows console encoding and set unbuffered mode
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

# Configure logging to be unbuffered and show real-time logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ],
    force=True  # Override any existing configuration
)

# Make sure the handler flushes immediately
for handler in logging.root.handlers:
    handler.setLevel(logging.INFO)
    # Force unbuffered output - flush after each write
    if hasattr(handler, 'stream'):
        try:
            handler.stream.reconfigure(line_buffering=True)
        except (AttributeError, ValueError):
            pass  # Some streams don't support reconfigure

# Set logging to flush immediately
logging.root.setLevel(logging.INFO)

from app.routes import api_router
from app.routes.config import STATIC_DIR

# Initialize FastAPI app
app = FastAPI(
    title="FIR Legal Analysis API",
    description="API for analyzing FIR documents and mapping legal sections",
    version="1.0.0"
)

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-change-in-production")

# Mount static files (JS, CSS, images, etc.)
if STATIC_DIR.exists():
    # Mount assets directory if it exists (contains bundled JS/CSS)
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir), html=False), name="assets")
    
    # Serve static files from root (for images like judgement.png, police_logo.png, etc.)
    # This allows accessing /judgement.png directly instead of /static/judgement.png
    @app.get("/{filename:path}.{ext}")
    async def serve_static_files(filename: str, ext: str):
        """Serve static files (images, svg, etc.) from the static directory."""
        # Only serve common static file extensions
        allowed_extensions = ['png', 'jpg', 'jpeg', 'svg', 'ico', 'gif', 'webp']
        if ext.lower() in allowed_extensions:
            file_path = STATIC_DIR / f"{filename}.{ext}"
            if file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
        return None

# Include API routes
app.include_router(api_router)

# Serve React app for all non-API routes (SPA routing)
@app.get("/{full_path:path}")
async def serve_react_app(full_path: str, request: Request):
    """
    Serve React app for all routes that don't match API endpoints.
    This enables client-side routing.
    """
    # Don't serve React app for API routes or static files
    if full_path.startswith(("api/", "upload", "results/", "assets/", "docs", "openapi.json")):
        return None
    
    # Don't serve React app for static file extensions
    static_extensions = ('.png', '.jpg', '.jpeg', '.svg', '.ico', '.gif', '.webp', '.css', '.js')
    if any(full_path.endswith(ext) for ext in static_extensions):
        return None
    
    # Serve index.html for all other routes (React Router will handle routing)
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    else:
        # Fallback if React app hasn't been built yet
        return {"message": "React app not built. Run 'npm run build' in the frontend directory."}


def main():
    """Launch the FastAPI application server."""
    print("=" * 80)
    print("🚀 Starting FIR Legal Analysis API Server")
    print("=" * 80)
    print("📄 API Documentation: http://localhost:8000/docs")
    print("📋 Upload Page: http://localhost:8000/")
    print("=" * 80)
    
    # Use string reference for reload to work properly
    uvicorn.run(
        "main:app",  # String reference required for auto-reload
        host="0.0.0.0",
        port=8000,
        reload=False,  # Enable auto-reload during development
        log_level="info"
    )


if __name__ == "__main__":
    main()

"""FastAPI application entry point for WatchQueue."""

import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import get_settings
from app.database import Database
from app.routers import (
    rooms_router,
    auth_router,
    queue_router,
    voting_router,
    websocket_router,
    sse_router,
)

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent
STATIC_DIR = PROJECT_ROOT / "static"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info("Starting WatchQueue API...")
    await Database.connect()
    logger.info("WatchQueue API started successfully")

    yield

    # Shutdown
    logger.info("Shutting down WatchQueue API...")
    await Database.disconnect()
    logger.info("WatchQueue API shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="WatchQueue API",
        description="Decide What to Watch with Friends - A collaborative movie/show selection system",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(rooms_router, prefix="/api")
    app.include_router(auth_router, prefix="/api")
    app.include_router(queue_router, prefix="/api")
    app.include_router(voting_router, prefix="/api")
    app.include_router(websocket_router)
    app.include_router(sse_router, prefix="/api")

    # Mount static files
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def root():
        """Serve the main web application."""
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/app")
    async def app_redirect():
        """Redirect to main app."""
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        try:
            # Check database connection
            db = Database.get_db()
            await db.command("ping")
            return {
                "status": "healthy",
                "database": "connected",
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e),
            }

    return app


# Create app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )

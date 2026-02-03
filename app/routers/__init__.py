"""API routers for WatchQueue."""

from app.routers.rooms import router as rooms_router
from app.routers.queue import router as queue_router
from app.routers.voting import router as voting_router
from app.routers.websocket import router as websocket_router
from app.routers.sse import router as sse_router

__all__ = [
    "rooms_router",
    "queue_router",
    "voting_router",
    "websocket_router",
    "sse_router",
]

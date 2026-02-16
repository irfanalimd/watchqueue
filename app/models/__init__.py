"""Pydantic models for WatchQueue."""

from app.models.room import (
    Member,
    RoomSettings,
    Room,
    RoomCreate,
    RoomUpdate,
    RoomInDB,
    SelectionMode,
)
from app.models.queue_item import (
    QueueItem,
    QueueItemCreate,
    QueueItemUpdate,
    QueueItemInDB,
    QueueItemStatus,
)
from app.models.vote import (
    Vote,
    VoteCreate,
    VoteType,
)
from app.models.watch_history import (
    WatchHistory,
    WatchHistoryCreate,
    WatchHistoryInDB,
)
from app.models.reaction import (
    ReactionCreate,
    ALLOWED_REACTIONS,
    REACTION_EMOJI_MAP,
)
from app.models.auth import (
    GoogleAuthRequest,
    AuthUser,
    AuthSessionResponse,
    AuthConfigResponse,
)

__all__ = [
    # Room models
    "Member",
    "RoomSettings",
    "Room",
    "RoomCreate",
    "RoomUpdate",
    "RoomInDB",
    "SelectionMode",
    # Queue item models
    "QueueItem",
    "QueueItemCreate",
    "QueueItemUpdate",
    "QueueItemInDB",
    "QueueItemStatus",
    # Vote models
    "Vote",
    "VoteCreate",
    "VoteType",
    # Watch history models
    "WatchHistory",
    "WatchHistoryCreate",
    "WatchHistoryInDB",
    # Reaction models
    "ReactionCreate",
    "ALLOWED_REACTIONS",
    "REACTION_EMOJI_MAP",
    # Auth models
    "GoogleAuthRequest",
    "AuthUser",
    "AuthSessionResponse",
    "AuthConfigResponse",
]

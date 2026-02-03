"""Queue item models for WatchQueue."""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from bson import ObjectId


class QueueItemStatus(str, Enum):
    """Status of a queue item."""
    QUEUED = "queued"
    WATCHING = "watching"
    WATCHED = "watched"
    REMOVED = "removed"


class QueueItemBase(BaseModel):
    """Base queue item model."""
    title: str = Field(..., min_length=1, max_length=500)


class QueueItemCreate(QueueItemBase):
    """Model for creating a queue item."""
    room_id: str = Field(..., min_length=1)
    added_by: str = Field(..., min_length=1, max_length=50)
    tmdb_id: int | None = None
    poster_url: str | None = None
    year: int | None = None
    runtime_minutes: int | None = None
    genres: list[str] | None = None
    overview: str | None = None
    vote_average: float | None = None


class QueueItemUpdate(BaseModel):
    """Model for updating a queue item."""
    status: QueueItemStatus | None = None
    poster_url: str | None = None
    year: int | None = Field(default=None, ge=1800, le=2100)
    runtime_minutes: int | None = Field(default=None, ge=1, le=1000)
    genres: list[str] | None = None
    streaming_on: list[str] | None = None

    model_config = {"extra": "forbid"}


class QueueItem(QueueItemBase):
    """Queue item model for API responses."""
    id: str = Field(..., alias="_id")
    room_id: str
    tmdb_id: int | None = None
    poster_url: str | None = None
    year: int | None = None
    runtime_minutes: int | None = None
    genres: list[str] = Field(default_factory=list)
    streaming_on: list[str] = Field(default_factory=list)
    added_by: str
    added_at: datetime
    status: QueueItemStatus = QueueItemStatus.QUEUED
    vote_score: int = 0
    upvotes: int = 0
    downvotes: int = 0
    overview: str | None = None
    vote_average: float | None = None

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }


class QueueItemInDB(BaseModel):
    """Queue item model as stored in database."""
    id: ObjectId = Field(default_factory=ObjectId, alias="_id")
    room_id: ObjectId
    title: str
    tmdb_id: int | None = None
    poster_url: str | None = None
    year: int | None = None
    runtime_minutes: int | None = None
    genres: list[str] = Field(default_factory=list)
    streaming_on: list[str] = Field(default_factory=list)
    added_by: str
    added_at: datetime = Field(default_factory=datetime.utcnow)
    status: QueueItemStatus = QueueItemStatus.QUEUED
    vote_score: int = 0
    upvotes: int = 0
    downvotes: int = 0
    overview: str | None = None
    vote_average: float | None = None

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }

    def to_response(self) -> QueueItem:
        """Convert to API response model."""
        return QueueItem(
            _id=str(self.id),
            room_id=str(self.room_id),
            title=self.title,
            tmdb_id=self.tmdb_id,
            poster_url=self.poster_url,
            year=self.year,
            runtime_minutes=self.runtime_minutes,
            genres=self.genres,
            streaming_on=self.streaming_on,
            added_by=self.added_by,
            added_at=self.added_at,
            status=self.status,
            vote_score=self.vote_score,
            upvotes=self.upvotes,
            downvotes=self.downvotes,
            overview=self.overview,
            vote_average=self.vote_average,
        )

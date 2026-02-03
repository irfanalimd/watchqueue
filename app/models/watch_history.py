"""Watch history models for WatchQueue."""

from datetime import datetime
from pydantic import BaseModel, Field
from bson import ObjectId


class WatchHistoryCreate(BaseModel):
    """Model for creating a watch history entry."""
    room_id: str = Field(..., min_length=1)
    item_id: str = Field(..., min_length=1)
    notes: str | None = Field(default=None, max_length=1000)

    model_config = {"extra": "forbid"}


class WatchHistory(BaseModel):
    """Watch history model for API responses."""
    id: str = Field(..., alias="_id")
    room_id: str
    item_id: str
    watched_at: datetime
    ratings: dict[str, int] = Field(default_factory=dict)
    notes: str | None = None

    model_config = {
        "populate_by_name": True,
        "extra": "forbid",
    }


class WatchHistoryInDB(BaseModel):
    """Watch history model as stored in database."""
    id: ObjectId = Field(default_factory=ObjectId, alias="_id")
    room_id: ObjectId
    item_id: ObjectId
    watched_at: datetime = Field(default_factory=datetime.utcnow)
    ratings: dict[str, int] = Field(default_factory=dict)
    notes: str | None = None

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }

    def to_response(self) -> WatchHistory:
        """Convert to API response model."""
        return WatchHistory(
            _id=str(self.id),
            room_id=str(self.room_id),
            item_id=str(self.item_id),
            watched_at=self.watched_at,
            ratings=self.ratings,
            notes=self.notes,
        )


class RatingUpdate(BaseModel):
    """Model for adding/updating a rating."""
    user_id: str = Field(..., min_length=1, max_length=50)
    rating: int = Field(..., ge=1, le=5)

    model_config = {"extra": "forbid"}

"""Room models for WatchQueue."""

from datetime import datetime
from enum import Enum
from typing import Annotated
from pydantic import BaseModel, Field
from bson import ObjectId


class SelectionMode(str, Enum):
    """Selection mode for choosing what to watch."""
    WEIGHTED_RANDOM = "weighted_random"
    HIGHEST_VOTES = "highest_votes"
    ROUND_ROBIN = "round_robin"


class Member(BaseModel):
    """A member of a room."""
    user_id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    avatar: str = Field(default="👤", max_length=10)

    model_config = {"extra": "forbid"}


class RoomSettings(BaseModel):
    """Settings for a room."""
    voting_duration_seconds: int = Field(default=60, ge=10, le=600)
    selection_mode: SelectionMode = Field(default=SelectionMode.WEIGHTED_RANDOM)
    allow_revotes: bool = Field(default=True)

    model_config = {"extra": "forbid"}


class RoomBase(BaseModel):
    """Base room model with common fields."""
    name: str = Field(..., min_length=1, max_length=200)

    model_config = {"extra": "forbid"}


class RoomCreate(RoomBase):
    """Model for creating a new room."""
    members: list[Member] = Field(default_factory=list, max_length=50)
    settings: RoomSettings = Field(default_factory=RoomSettings)


class RoomUpdate(BaseModel):
    """Model for updating a room."""
    name: str | None = Field(default=None, min_length=1, max_length=200)
    settings: RoomSettings | None = None

    model_config = {"extra": "forbid"}


class Room(RoomBase):
    """Room model for API responses."""
    id: str = Field(..., alias="_id")
    code: str = Field(..., min_length=4, max_length=10)
    members: list[Member] = Field(default_factory=list)
    settings: RoomSettings = Field(default_factory=RoomSettings)
    created_at: datetime

    model_config = {
        "populate_by_name": True,
        "extra": "forbid",
    }


class RoomInDB(BaseModel):
    """Room model as stored in database."""
    id: ObjectId = Field(default_factory=ObjectId, alias="_id")
    name: str
    code: str
    members: list[Member] = Field(default_factory=list)
    settings: RoomSettings = Field(default_factory=RoomSettings)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }

    def to_response(self) -> Room:
        """Convert to API response model."""
        return Room(
            _id=str(self.id),
            name=self.name,
            code=self.code,
            members=self.members,
            settings=self.settings,
            created_at=self.created_at,
        )

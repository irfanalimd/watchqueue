"""Vote models for WatchQueue."""

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class VoteType(str, Enum):
    """Type of vote."""
    UP = "up"
    DOWN = "down"


class VoteCreate(BaseModel):
    """Model for creating/updating a vote."""
    item_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1, max_length=50)
    vote: VoteType


class Vote(BaseModel):
    """Vote model for API responses."""
    item_id: str
    user_id: str
    vote: VoteType
    voted_at: datetime

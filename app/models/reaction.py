"""Reaction models for WatchQueue."""

from pydantic import BaseModel, Field, field_validator

ALLOWED_REACTIONS = ["fire", "sleepy", "laughing", "scream", "hundred"]

REACTION_EMOJI_MAP = {
    "fire": "🔥",
    "sleepy": "😴",
    "laughing": "😂",
    "scream": "😱",
    "hundred": "💯",
}


class ReactionCreate(BaseModel):
    """Model for creating/toggling an emoji reaction."""

    item_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1, max_length=50)
    reaction: str = Field(..., min_length=1, max_length=20)

    @field_validator("reaction")
    @classmethod
    def validate_reaction(cls, value: str) -> str:
        if value not in ALLOWED_REACTIONS:
            raise ValueError(f"Invalid reaction. Allowed: {', '.join(ALLOWED_REACTIONS)}")
        return value

"""Authentication models."""

from datetime import datetime
from pydantic import BaseModel, Field


class GoogleAuthRequest(BaseModel):
    """Request payload for Google auth exchange."""
    id_token: str = Field(..., min_length=20)


class AuthUser(BaseModel):
    """Authenticated user identity."""
    user_id: str = Field(..., min_length=1, max_length=128)
    email: str | None = None
    full_name: str | None = None
    picture: str | None = None


class AuthSessionResponse(BaseModel):
    """Response payload for successful authentication."""
    session_token: str
    expires_at: datetime
    user: AuthUser


class AuthConfigResponse(BaseModel):
    """Client-side auth configuration."""
    google_client_id: str | None = None

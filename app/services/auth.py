"""Authentication service for Google sign-in and app sessions."""

import secrets
from datetime import datetime, timedelta
from typing import Any
import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import get_settings
from app.models.auth import AuthUser


class AuthService:
    """Service for user authentication and session management."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.users = db.users
        self.sessions = db.sessions

    async def _fetch_google_token_info(self, id_token: str) -> dict[str, Any]:
        """Validate Google ID token via Google tokeninfo endpoint."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": id_token},
            )
            response.raise_for_status()
            return response.json()

    async def exchange_google_token(self, id_token: str) -> tuple[str, datetime, AuthUser]:
        """Exchange Google ID token for app session token."""
        payload = await self._fetch_google_token_info(id_token)
        google_sub = payload.get("sub")
        audience = payload.get("aud")
        if not google_sub:
            raise ValueError("Invalid Google token")

        settings = get_settings()
        if settings.google_client_id and audience != settings.google_client_id:
            raise ValueError("Google token audience mismatch")

        user_doc = {
            "google_sub": google_sub,
            "email": payload.get("email"),
            "full_name": payload.get("name"),
            "picture": payload.get("picture"),
            "updated_at": datetime.utcnow(),
        }
        await self.users.update_one(
            {"google_sub": google_sub},
            {"$set": user_doc, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True,
        )

        expires_at = datetime.utcnow() + timedelta(seconds=settings.auth_session_ttl_seconds)
        session_token = secrets.token_urlsafe(48)
        await self.sessions.insert_one(
            {
                "token": session_token,
                "user_id": google_sub,
                "created_at": datetime.utcnow(),
                "expires_at": expires_at,
            }
        )

        return session_token, expires_at, AuthUser(
            user_id=google_sub,
            email=payload.get("email"),
            full_name=payload.get("name"),
            picture=payload.get("picture"),
        )

    async def get_user_by_session(self, session_token: str) -> AuthUser | None:
        """Resolve authenticated user from app session token."""
        session_doc = await self.sessions.find_one({
            "token": session_token,
            "expires_at": {"$gt": datetime.utcnow()},
        })
        if not session_doc:
            return None

        user_doc = await self.users.find_one({"google_sub": session_doc["user_id"]})
        if not user_doc:
            return None

        return AuthUser(
            user_id=user_doc["google_sub"],
            email=user_doc.get("email"),
            full_name=user_doc.get("full_name"),
            picture=user_doc.get("picture"),
        )

    async def logout(self, session_token: str) -> bool:
        """Invalidate a session token."""
        result = await self.sessions.delete_one({"token": session_token})
        return result.deleted_count > 0

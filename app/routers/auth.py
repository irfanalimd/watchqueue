"""Authentication API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Header, status
from motor.motor_asyncio import AsyncIOMotorDatabase
import httpx

from app.config import get_settings
from app.database import get_database
from app.models.auth import (
    GoogleAuthRequest,
    AuthSessionResponse,
    AuthUser,
    AuthConfigResponse,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> AuthService:
    """Dependency for auth service."""
    return AuthService(db)


def _extract_session_token(
    x_session_token: str | None,
    authorization: str | None,
) -> str | None:
    if x_session_token:
        return x_session_token
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


async def get_current_user(
    x_session_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthUser:
    """Resolve current authenticated user."""
    session_token = _extract_session_token(x_session_token, authorization)
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    user = await auth_service.get_user_by_session(session_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )
    return user


@router.get("/config", response_model=AuthConfigResponse)
async def get_auth_config() -> AuthConfigResponse:
    """Return client-side auth config."""
    settings = get_settings()
    return AuthConfigResponse(
        google_client_id=settings.google_client_id or None,
    )


@router.post("/google", response_model=AuthSessionResponse)
async def auth_with_google(
    payload: GoogleAuthRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthSessionResponse:
    """Authenticate with Google ID token and create app session."""
    try:
        session_token, expires_at, user = await auth_service.exchange_google_token(payload.id_token)
    except httpx.HTTPError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Google token",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return AuthSessionResponse(
        session_token=session_token,
        expires_at=expires_at,
        user=user,
    )


@router.get("/me", response_model=AuthUser)
async def get_me(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    """Get authenticated user profile."""
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    x_session_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    """Log out current user."""
    session_token = _extract_session_token(x_session_token, authorization)
    if not session_token:
        return
    await auth_service.logout(session_token)

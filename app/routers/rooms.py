"""Room management API endpoints."""

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.config import get_settings
from app.models.room import Room, RoomCreate, RoomUpdate, Member
from app.models.auth import AuthUser
from app.services.rooms import RoomService
from app.routers.auth import get_current_user

router = APIRouter(prefix="/rooms", tags=["rooms"])


class AdminGrantRequest(BaseModel):
    """Request to grant admin privileges."""
    acting_user_id: str = Field(..., min_length=1)
    target_user_id: str = Field(..., min_length=1)


class LeaveRoomRequest(BaseModel):
    """Request to leave a room."""
    user_id: str = Field(..., min_length=1)
    new_admin_user_id: str | None = Field(default=None, min_length=1)


class RoomCreateAuthRequest(BaseModel):
    """Create room as authenticated user."""
    name: str = Field(..., min_length=1, max_length=200)
    display_name: str = Field(..., min_length=1, max_length=100)
    avatar: str = Field(default="👤", max_length=10)
    region: str = Field(default="US", min_length=2, max_length=2)


class RoomJoinAuthRequest(BaseModel):
    """Join room as authenticated user."""
    display_name: str = Field(..., min_length=1, max_length=100)
    avatar: str = Field(default="👤", max_length=10)
    region: str = Field(default="US", min_length=2, max_length=2)


def get_room_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> RoomService:
    """Dependency for room service."""
    return RoomService(db)


def _ensure_legacy_room_flows_allowed() -> None:
    """Block unauthenticated create/join when Google auth mode is enabled."""
    settings = get_settings()
    if settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Use Google authenticated room endpoints",
        )


@router.post("", response_model=Room, status_code=status.HTTP_201_CREATED)
async def create_room(
    room_data: RoomCreate,
    service: RoomService = Depends(get_room_service),
) -> Room:
    """Create a new watch room.

    Returns the created room with a unique join code.
    """
    _ensure_legacy_room_flows_allowed()
    try:
        return await service.create_room(room_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/auth/create", response_model=Room, status_code=status.HTTP_201_CREATED)
async def create_room_auth(
    payload: RoomCreateAuthRequest,
    user: AuthUser = Depends(get_current_user),
    service: RoomService = Depends(get_room_service),
) -> Room:
    """Create room as authenticated Google user."""
    room_data = RoomCreate(
        name=payload.name,
        members=[
            Member(
                user_id=user.user_id,
                name=payload.display_name,
                avatar=payload.avatar,
                region=payload.region,
            )
        ],
    )
    try:
        return await service.create_room(room_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{room_id}", response_model=Room)
async def get_room(
    room_id: str,
    service: RoomService = Depends(get_room_service),
) -> Room:
    """Get a room by ID."""
    room = await service.get_room(room_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    return room


@router.get("/code/{code}", response_model=Room)
async def get_room_by_code(
    code: str,
    service: RoomService = Depends(get_room_service),
) -> Room:
    """Get a room by its join code."""
    room = await service.get_room_by_code(code)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    return room


@router.patch("/{room_id}", response_model=Room)
async def update_room(
    room_id: str,
    room_update: RoomUpdate,
    service: RoomService = Depends(get_room_service),
) -> Room:
    """Update a room's name or settings."""
    room = await service.update_room(room_id, room_update)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    return room


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: str,
    acting_user_id: str = Query(..., min_length=1),
    service: RoomService = Depends(get_room_service),
) -> None:
    """Delete a room and all associated data."""
    is_admin = await service.is_admin(room_id, acting_user_id)
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only room admins can delete the room",
        )
    deleted = await service.delete_room(room_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )


@router.post("/{room_id}/members", response_model=Room)
async def add_member(
    room_id: str,
    member: Member,
    service: RoomService = Depends(get_room_service),
) -> Room:
    """Add a member to a room."""
    try:
        room = await service.add_member(room_id, member)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    return room


@router.delete("/{room_id}/members/{user_id}", response_model=Room)
async def remove_member(
    room_id: str,
    user_id: str,
    acting_user_id: str = Query(..., min_length=1),
    new_admin_user_id: str | None = Query(default=None),
    service: RoomService = Depends(get_room_service),
) -> Room:
    """Remove a member from a room."""
    if acting_user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Users can only remove themselves from a room",
        )
    try:
        room = await service.leave_room(room_id, user_id, new_admin_user_id=new_admin_user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    return room


@router.put("/{room_id}/members/{user_id}", response_model=Room)
async def update_member(
    room_id: str,
    user_id: str,
    member: Member,
    service: RoomService = Depends(get_room_service),
) -> Room:
    """Update a member's info (name, avatar)."""
    if member.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User ID in path must match member user_id",
        )
    try:
        room = await service.update_member(room_id, member)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room or member not found",
        )
    return room


@router.post("/{code}/join", response_model=Room)
async def join_room(
    code: str,
    member: Member,
    service: RoomService = Depends(get_room_service),
) -> Room:
    """Join a room using its code."""
    _ensure_legacy_room_flows_allowed()
    room = await service.get_room_by_code(code)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    try:
        updated_room = await service.add_member(room.id, member)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    if not updated_room:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to join room",
        )
    return updated_room


@router.post("/{code}/auth-join", response_model=Room)
async def join_room_auth(
    code: str,
    payload: RoomJoinAuthRequest,
    user: AuthUser = Depends(get_current_user),
    service: RoomService = Depends(get_room_service),
) -> Room:
    """Join a room using authenticated Google identity."""
    room = await service.get_room_by_code(code)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    member = Member(
        user_id=user.user_id,
        name=payload.display_name,
        avatar=payload.avatar,
        region=payload.region,
    )
    try:
        updated_room = await service.add_member(room.id, member)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    if not updated_room:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to join room",
        )
    return updated_room


@router.get("/member/{user_id}", response_model=list[Room])
async def list_rooms_for_member(
    user_id: str,
    service: RoomService = Depends(get_room_service),
) -> list[Room]:
    """List all rooms for a member."""
    return await service.list_rooms_for_member(user_id)


@router.get("/auth/me", response_model=list[Room])
async def list_my_rooms(
    user: AuthUser = Depends(get_current_user),
    service: RoomService = Depends(get_room_service),
) -> list[Room]:
    """List all rooms for currently authenticated user."""
    return await service.list_rooms_for_member(user.user_id)


@router.post("/{room_id}/admins", response_model=Room)
async def grant_admin(
    room_id: str,
    request: AdminGrantRequest,
    service: RoomService = Depends(get_room_service),
) -> Room:
    """Grant admin privileges to a room member."""
    if not await service.is_admin(room_id, request.acting_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only room admins can grant admin privileges",
        )
    room = await service.grant_admin(room_id, request.target_user_id)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room or target member not found",
        )
    return room


@router.post("/{room_id}/leave", response_model=Room)
async def leave_room(
    room_id: str,
    request: LeaveRoomRequest,
    service: RoomService = Depends(get_room_service),
) -> Room:
    """Leave a room. Last admin must transfer admin first."""
    try:
        room = await service.leave_room(
            room_id,
            request.user_id,
            new_admin_user_id=request.new_admin_user_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found or user not in room",
        )
    return room

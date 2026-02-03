"""Room management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database import get_database
from app.models.room import Room, RoomCreate, RoomUpdate, Member
from app.services.rooms import RoomService

router = APIRouter(prefix="/rooms", tags=["rooms"])


def get_room_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> RoomService:
    """Dependency for room service."""
    return RoomService(db)


@router.post("", response_model=Room, status_code=status.HTTP_201_CREATED)
async def create_room(
    room_data: RoomCreate,
    service: RoomService = Depends(get_room_service),
) -> Room:
    """Create a new watch room.

    Returns the created room with a unique join code.
    """
    return await service.create_room(room_data)


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
    service: RoomService = Depends(get_room_service),
) -> None:
    """Delete a room and all associated data."""
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
    room = await service.add_member(room_id, member)
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
    service: RoomService = Depends(get_room_service),
) -> Room:
    """Remove a member from a room."""
    room = await service.remove_member(room_id, user_id)
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
    room = await service.update_member(room_id, member)
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
    room = await service.get_room_by_code(code)
    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    updated_room = await service.add_member(room.id, member)
    if not updated_room:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to join room",
        )
    return updated_room

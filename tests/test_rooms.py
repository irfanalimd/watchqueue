"""Tests for room management."""

import pytest
from httpx import AsyncClient

from app.models.room import RoomCreate, RoomUpdate, RoomSettings, Member, SelectionMode
from app.services.rooms import RoomService


class TestRoomService:
    """Tests for RoomService."""

    async def test_create_room(self, room_service: RoomService):
        """Test creating a new room."""
        room_data = RoomCreate(
            name="Test Room",
            members=[Member(user_id="user1", name="User 1", avatar="👤")],
        )

        room = await room_service.create_room(room_data)

        assert room.name == "Test Room"
        assert len(room.code) == 6
        assert len(room.members) == 1
        assert room.members[0].user_id == "user1"
        assert room.settings.selection_mode == SelectionMode.WEIGHTED_RANDOM

    async def test_create_room_unique_code(self, room_service: RoomService):
        """Test that each room gets a unique code."""
        rooms = []
        for i in range(5):
            room = await room_service.create_room(
                RoomCreate(name=f"Room {i}")
            )
            rooms.append(room)

        codes = [r.code for r in rooms]
        assert len(codes) == len(set(codes)), "Room codes should be unique"

    async def test_get_room_by_id(self, room_service: RoomService, movie_room: dict):
        """Test getting a room by ID."""
        room = await room_service.get_room(movie_room["_id"])

        assert room is not None
        assert room.name == "Friday Night Movies"
        assert len(room.members) == 4

    async def test_get_room_by_code(self, room_service: RoomService, movie_room: dict):
        """Test getting a room by join code."""
        room = await room_service.get_room_by_code(movie_room["code"])

        assert room is not None
        assert room.id == movie_room["_id"]

    async def test_get_room_not_found(self, room_service: RoomService):
        """Test getting a non-existent room."""
        room = await room_service.get_room("000000000000000000000000")
        assert room is None

    async def test_update_room_name(self, room_service: RoomService, movie_room: dict):
        """Test updating a room's name."""
        room = await room_service.update_room(
            movie_room["_id"],
            RoomUpdate(name="Saturday Night Movies"),
        )

        assert room is not None
        assert room.name == "Saturday Night Movies"

    async def test_update_room_settings(self, room_service: RoomService, movie_room: dict):
        """Test updating room settings."""
        new_settings = RoomSettings(
            voting_duration_seconds=120,
            selection_mode=SelectionMode.HIGHEST_VOTES,
            allow_revotes=False,
        )

        room = await room_service.update_room(
            movie_room["_id"],
            RoomUpdate(settings=new_settings),
        )

        assert room is not None
        assert room.settings.voting_duration_seconds == 120
        assert room.settings.selection_mode == SelectionMode.HIGHEST_VOTES
        assert room.settings.allow_revotes is False

    async def test_add_member(self, room_service: RoomService, movie_room: dict):
        """Test adding a member to a room."""
        new_member = Member(user_id="eve", name="Eve", avatar="🦄")
        room = await room_service.add_member(movie_room["_id"], new_member)

        assert room is not None
        assert len(room.members) == 5
        assert any(m.user_id == "eve" for m in room.members)

    async def test_add_duplicate_member(self, room_service: RoomService, movie_room: dict):
        """Test adding an existing member (should return current state)."""
        member = Member(user_id="alice", name="Alice Updated", avatar="🦊")
        room = await room_service.add_member(movie_room["_id"], member)

        assert room is not None
        assert len(room.members) == 4  # No duplicate added

    async def test_remove_member(self, room_service: RoomService, movie_room: dict):
        """Test removing a member from a room."""
        room = await room_service.remove_member(movie_room["_id"], "charlie")

        assert room is not None
        assert len(room.members) == 3
        assert not any(m.user_id == "charlie" for m in room.members)

    async def test_is_member(self, room_service: RoomService, movie_room: dict):
        """Test checking if user is a member."""
        assert await room_service.is_member(movie_room["_id"], "alice") is True
        assert await room_service.is_member(movie_room["_id"], "unknown") is False

    async def test_delete_room(self, room_service: RoomService, movie_room: dict):
        """Test deleting a room."""
        deleted = await room_service.delete_room(movie_room["_id"])
        assert deleted is True

        room = await room_service.get_room(movie_room["_id"])
        assert room is None


class TestRoomAPI:
    """Tests for room API endpoints."""

    async def test_create_room_api(self, client: AsyncClient):
        """Test POST /api/rooms endpoint."""
        response = await client.post(
            "/api/rooms",
            json={
                "name": "API Test Room",
                "members": [{"user_id": "test", "name": "Test User", "avatar": "👤"}],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "API Test Room"
        assert "code" in data
        assert "_id" in data

    async def test_get_room_api(self, client: AsyncClient, movie_room: dict):
        """Test GET /api/rooms/{room_id} endpoint."""
        response = await client.get(f"/api/rooms/{movie_room['_id']}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Friday Night Movies"

    async def test_get_room_by_code_api(self, client: AsyncClient, movie_room: dict):
        """Test GET /api/rooms/code/{code} endpoint."""
        response = await client.get(f"/api/rooms/code/{movie_room['code']}")

        assert response.status_code == 200
        data = response.json()
        assert data["_id"] == movie_room["_id"]

    async def test_join_room_api(self, client: AsyncClient, movie_room: dict):
        """Test POST /api/rooms/{code}/join endpoint."""
        response = await client.post(
            f"/api/rooms/{movie_room['code']}/join",
            json={"user_id": "newbie", "name": "Newbie", "avatar": "🆕"},
        )

        assert response.status_code == 200
        data = response.json()
        assert any(m["user_id"] == "newbie" for m in data["members"])

    async def test_update_room_api(self, client: AsyncClient, movie_room: dict):
        """Test PATCH /api/rooms/{room_id} endpoint."""
        response = await client.patch(
            f"/api/rooms/{movie_room['_id']}",
            json={"name": "Updated Room Name"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Room Name"

    async def test_delete_room_api(self, client: AsyncClient, movie_room: dict):
        """Test DELETE /api/rooms/{room_id} endpoint."""
        response = await client.delete(f"/api/rooms/{movie_room['_id']}")
        assert response.status_code == 204

        response = await client.get(f"/api/rooms/{movie_room['_id']}")
        assert response.status_code == 404

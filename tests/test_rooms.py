"""Tests for room management."""

import pytest
from datetime import datetime
from httpx import AsyncClient

from app.models.room import RoomCreate, RoomUpdate, RoomSettings, Member, SelectionMode
from app.services.rooms import RoomService
from app.database import Database


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
        assert room.admins == ["user1"]
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

    async def test_create_room_duplicate_name_rejected(self, room_service: RoomService):
        """Room names should be unique (case-insensitive)."""
        await room_service.create_room(RoomCreate(name="Movie Club"))
        with pytest.raises(ValueError, match="Room name already exists"):
            await room_service.create_room(RoomCreate(name="movie club"))

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

    async def test_add_member_duplicate_name_rejected(self, room_service: RoomService, movie_room: dict):
        """Adding a new user with existing name should fail."""
        member = Member(user_id="eve", name="Alice", avatar="🦄")
        with pytest.raises(ValueError, match="User already exists"):
            await room_service.add_member(movie_room["_id"], member)

    async def test_remove_member(self, room_service: RoomService, movie_room: dict):
        """Test removing a member from a room."""
        room = await room_service.remove_member(movie_room["_id"], "charlie")

        assert room is not None
        assert len(room.members) == 3
        assert not any(m.user_id == "charlie" for m in room.members)

    async def test_leave_room_requires_admin_transfer(self, room_service: RoomService, movie_room: dict):
        """Last admin cannot leave without transfer."""
        with pytest.raises(ValueError, match="Last admin cannot leave"):
            await room_service.leave_room(movie_room["_id"], "alice")

    async def test_leave_room_with_admin_transfer(self, room_service: RoomService, movie_room: dict):
        """Last admin can leave with transfer target."""
        room = await room_service.leave_room(
            movie_room["_id"],
            "alice",
            new_admin_user_id="bob",
        )
        assert room is not None
        assert "alice" not in [m.user_id for m in room.members]
        assert "bob" in room.admins

    async def test_leave_room_is_idempotent_for_non_member(self, room_service: RoomService, movie_room: dict):
        """Leaving a room twice should not fail for stale clients."""
        first = await room_service.leave_room(movie_room["_id"], "bob")
        assert first is not None
        second = await room_service.leave_room(movie_room["_id"], "bob")
        assert second is not None

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

    async def test_create_room_duplicate_name_api(self, client: AsyncClient):
        """Duplicate room names should be rejected."""
        first = await client.post(
            "/api/rooms",
            json={
                "name": "API Duplicate Room",
                "members": [{"user_id": "test", "name": "Test User", "avatar": "👤"}],
            },
        )
        assert first.status_code == 201

        second = await client.post(
            "/api/rooms",
            json={
                "name": "api duplicate room",
                "members": [{"user_id": "test2", "name": "Test User 2", "avatar": "👤"}],
            },
        )
        assert second.status_code == 400
        assert "Room name already exists" in second.json()["detail"]

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

    async def test_join_room_duplicate_name_api(self, client: AsyncClient, movie_room: dict):
        """Joining with an existing display name should be rejected."""
        response = await client.post(
            f"/api/rooms/{movie_room['code']}/join",
            json={"user_id": "new_user", "name": "alice", "avatar": "🆕"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "User already exists" in data["detail"]

    async def test_update_room_api(self, client: AsyncClient, movie_room: dict):
        """Test PATCH /api/rooms/{room_id} endpoint."""
        response = await client.patch(
            f"/api/rooms/{movie_room['_id']}",
            json={"name": "Updated Room Name"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Room Name"

    async def test_update_member_api(self, client: AsyncClient, movie_room: dict):
        """Member profile can be updated explicitly via API."""
        response = await client.put(
            f"/api/rooms/{movie_room['_id']}/members/alice",
            json={
                "user_id": "alice",
                "name": "Alice Prime",
                "avatar": "🐼",
                "region": "US",
            },
        )
        assert response.status_code == 200
        data = response.json()
        alice = next(m for m in data["members"] if m["user_id"] == "alice")
        assert alice["name"] == "Alice Prime"
        assert alice["avatar"] == "🐼"

    async def test_delete_room_api(self, client: AsyncClient, movie_room: dict):
        """Test DELETE /api/rooms/{room_id} endpoint."""
        response = await client.delete(
            f"/api/rooms/{movie_room['_id']}?acting_user_id=alice"
        )
        assert response.status_code == 204

        response = await client.get(f"/api/rooms/{movie_room['_id']}")
        assert response.status_code == 404

    async def test_delete_room_requires_admin(self, client: AsyncClient, movie_room: dict):
        """Non-admin users cannot delete rooms."""
        response = await client.delete(
            f"/api/rooms/{movie_room['_id']}?acting_user_id=bob"
        )
        assert response.status_code == 403

    async def test_grant_admin_api(self, client: AsyncClient, movie_room: dict):
        """Admin can grant admin privileges."""
        response = await client.post(
            f"/api/rooms/{movie_room['_id']}/admins",
            json={
                "acting_user_id": "alice",
                "target_user_id": "bob",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "bob" in data["admins"]

    async def test_leave_room_requires_transfer_for_last_admin(
        self,
        client: AsyncClient,
        movie_room: dict,
    ):
        """Last admin must transfer admin before leaving."""
        response = await client.post(
            f"/api/rooms/{movie_room['_id']}/leave",
            json={"user_id": "alice"},
        )
        assert response.status_code == 400
        assert "Last admin cannot leave" in response.json()["detail"]

    async def test_leave_room_with_admin_transfer(
        self,
        client: AsyncClient,
        movie_room: dict,
    ):
        """Last admin can leave after transferring admin."""
        response = await client.post(
            f"/api/rooms/{movie_room['_id']}/leave",
            json={"user_id": "alice", "new_admin_user_id": "bob"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "alice" not in [m["user_id"] for m in data["members"]]
        assert "bob" in data["admins"]

    async def test_list_rooms_for_member_api(self, client: AsyncClient, movie_room: dict):
        """Member can fetch all their rooms."""
        response = await client.get("/api/rooms/member/alice")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(room["_id"] == movie_room["_id"] for room in data)
        assert all("admins" in room for room in data)

    async def test_leave_room_removes_from_member_room_list_api(self, client: AsyncClient, movie_room: dict):
        """Leaving a room should remove it from that user's room list."""
        leave = await client.post(
            f"/api/rooms/{movie_room['_id']}/leave",
            json={"user_id": "bob"},
        )
        assert leave.status_code == 200

        rooms = await client.get("/api/rooms/member/bob")
        assert rooms.status_code == 200
        data = rooms.json()
        assert all(room["_id"] != movie_room["_id"] for room in data)

    async def test_database_migration_backfills_admin_and_region(self, db):
        """Startup migration should backfill admins and member region on legacy rooms."""
        await db.rooms.insert_one({
            "name": "Legacy Room",
            "code": "LEGACY",
            "members": [{"user_id": "legacy_user", "name": "Legacy", "avatar": "👤"}],
            "settings": {
                "voting_duration_seconds": 60,
                "selection_mode": "weighted_random",
                "allow_revotes": True,
            },
            "created_at": datetime.utcnow(),
        })

        await Database.run_migrations()
        room = await db.rooms.find_one({"code": "LEGACY"})
        assert room is not None
        assert room["admins"] == ["legacy_user"]
        assert room["members"][0]["region"] == "US"

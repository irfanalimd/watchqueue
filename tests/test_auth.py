"""Core tests for Google auth and authenticated room flows."""

from httpx import AsyncClient

from app.services.auth import AuthService
from app.config import get_settings


class TestAuthAPI:
    """Core authentication API tests."""

    async def test_google_auth_exchange_and_me(self, client: AsyncClient, monkeypatch):
        """Google token exchange should create a session and resolve /me."""
        async def fake_tokeninfo(self, _id_token: str):
            return {
                "sub": "google_sub_123",
                "aud": get_settings().google_client_id,
                "email": "user@example.com",
                "name": "Google User",
                "picture": "https://example.com/pic.png",
            }

        monkeypatch.setattr(AuthService, "_fetch_google_token_info", fake_tokeninfo)

        login = await client.post(
            "/api/auth/google",
            json={"id_token": "dummy_google_id_token_value_1234567890"},
        )
        assert login.status_code == 200
        payload = login.json()
        assert payload["user"]["user_id"] == "google_sub_123"
        assert payload["session_token"]

        me = await client.get(
            "/api/auth/me",
            headers={"X-Session-Token": payload["session_token"]},
        )
        assert me.status_code == 200
        assert me.json()["email"] == "user@example.com"

    async def test_authenticated_room_create_and_rejoin_is_idempotent(
        self,
        client: AsyncClient,
        monkeypatch,
    ):
        """Authenticated rejoin should not silently overwrite existing room profile."""
        async def fake_tokeninfo(self, _id_token: str):
            return {
                "sub": "google_sub_777",
                "aud": get_settings().google_client_id,
                "email": "same@example.com",
                "name": "Same Person",
            }

        monkeypatch.setattr(AuthService, "_fetch_google_token_info", fake_tokeninfo)

        login = await client.post(
            "/api/auth/google",
            json={"id_token": "dummy_google_id_token_value_7777777777"},
        )
        token = login.json()["session_token"]
        headers = {"X-Session-Token": token}

        created = await client.post(
            "/api/rooms/auth/create",
            headers=headers,
            json={
                "name": "Auth Room",
                "display_name": "AlphaName",
                "avatar": "😀",
                "region": "US",
            },
        )
        assert created.status_code == 201
        room = created.json()
        assert room["members"][0]["name"] == "AlphaName"

        rejoin = await client.post(
            f"/api/rooms/{room['code']}/auth-join",
            headers=headers,
            json={
                "display_name": "BetaName",
                "avatar": "🦊",
                "region": "US",
            },
        )
        assert rejoin.status_code == 200
        updated = rejoin.json()
        same_user_members = [m for m in updated["members"] if m["user_id"] == "google_sub_777"]
        assert len(same_user_members) == 1
        assert same_user_members[0]["name"] == "AlphaName"

        my_rooms = await client.get("/api/rooms/auth/me", headers=headers)
        assert my_rooms.status_code == 200
        assert any(r["_id"] == room["_id"] for r in my_rooms.json())

    async def test_authenticated_create_room_duplicate_name_rejected(
        self,
        client: AsyncClient,
        monkeypatch,
    ):
        """Authenticated room create should also enforce unique room names."""
        async def fake_tokeninfo(self, _id_token: str):
            return {
                "sub": "google_sub_dup",
                "aud": get_settings().google_client_id,
                "email": "dup@example.com",
                "name": "Dup User",
            }

        monkeypatch.setattr(AuthService, "_fetch_google_token_info", fake_tokeninfo)

        login = await client.post(
            "/api/auth/google",
            json={"id_token": "dummy_google_id_token_dup_1234567890"},
        )
        token = login.json()["session_token"]
        headers = {"X-Session-Token": token}

        first = await client.post(
            "/api/rooms/auth/create",
            headers=headers,
            json={
                "name": "Duplicate Auth Room",
                "display_name": "First",
                "avatar": "😀",
                "region": "US",
            },
        )
        assert first.status_code == 201

        second = await client.post(
            "/api/rooms/auth/create",
            headers=headers,
            json={
                "name": "duplicate auth room",
                "display_name": "Second",
                "avatar": "🦊",
                "region": "US",
            },
        )
        assert second.status_code == 400
        assert "Room name already exists" in second.json()["detail"]

"""Tests for watch history tracking."""

import pytest
from httpx import AsyncClient

from app.models.watch_history import WatchHistoryCreate
from app.services.history import HistoryService
from app.services.queue import QueueService


class TestHistoryService:
    """Tests for HistoryService."""

    async def test_mark_as_watched(
        self,
        history_service: HistoryService,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test marking an item as watched."""
        item = queue_with_items["items"][0]
        room_id = queue_with_items["room"]["_id"]

        history = await history_service.mark_as_watched(WatchHistoryCreate(
            room_id=room_id,
            item_id=item.id,
            notes="Great movie night!",
        ))

        assert history.item_id == item.id
        assert history.room_id == room_id
        assert history.notes == "Great movie night!"
        assert history.ratings == {}

        # Queue item status should be updated
        updated_item = await queue_service.get_item(item.id)
        assert updated_item.status.value == "watched"

    async def test_mark_as_watched_duplicate(
        self,
        history_service: HistoryService,
        queue_with_items: dict,
    ):
        """Test that marking same item twice returns existing history."""
        item = queue_with_items["items"][0]
        room_id = queue_with_items["room"]["_id"]

        history1 = await history_service.mark_as_watched(WatchHistoryCreate(
            room_id=room_id,
            item_id=item.id,
        ))

        history2 = await history_service.mark_as_watched(WatchHistoryCreate(
            room_id=room_id,
            item_id=item.id,
            notes="Different notes",
        ))

        assert history1.id == history2.id

    async def test_add_rating(
        self,
        history_service: HistoryService,
        queue_with_items: dict,
    ):
        """Test adding ratings to a watched item."""
        item = queue_with_items["items"][0]
        room_id = queue_with_items["room"]["_id"]

        history = await history_service.mark_as_watched(WatchHistoryCreate(
            room_id=room_id,
            item_id=item.id,
        ))

        # Add ratings
        history = await history_service.add_rating(history.id, "alice", 5)
        history = await history_service.add_rating(history.id, "bob", 4)
        history = await history_service.add_rating(history.id, "charlie", 3)

        assert history.ratings["alice"] == 5
        assert history.ratings["bob"] == 4
        assert history.ratings["charlie"] == 3

    async def test_update_rating(
        self,
        history_service: HistoryService,
        queue_with_items: dict,
    ):
        """Test updating an existing rating."""
        item = queue_with_items["items"][0]
        room_id = queue_with_items["room"]["_id"]

        history = await history_service.mark_as_watched(WatchHistoryCreate(
            room_id=room_id,
            item_id=item.id,
        ))

        await history_service.add_rating(history.id, "alice", 3)
        history = await history_service.add_rating(history.id, "alice", 5)

        assert history.ratings["alice"] == 5

    async def test_rating_validation(
        self,
        history_service: HistoryService,
        queue_with_items: dict,
    ):
        """Test that invalid ratings are rejected."""
        item = queue_with_items["items"][0]
        room_id = queue_with_items["room"]["_id"]

        history = await history_service.mark_as_watched(WatchHistoryCreate(
            room_id=room_id,
            item_id=item.id,
        ))

        with pytest.raises(ValueError, match="between 1 and 5"):
            await history_service.add_rating(history.id, "alice", 0)

        with pytest.raises(ValueError, match="between 1 and 5"):
            await history_service.add_rating(history.id, "alice", 6)

    async def test_get_room_history(
        self,
        history_service: HistoryService,
        queue_with_items: dict,
    ):
        """Test getting watch history for a room."""
        room_id = queue_with_items["room"]["_id"]
        items = queue_with_items["items"]

        # Mark several items as watched
        for item in items[:3]:
            await history_service.mark_as_watched(WatchHistoryCreate(
                room_id=room_id,
                item_id=item.id,
            ))

        history = await history_service.get_room_history(room_id)

        assert len(history) == 3
        # Should be ordered by watched_at descending
        assert history[0].item_id == items[2].id

    async def test_update_notes(
        self,
        history_service: HistoryService,
        queue_with_items: dict,
    ):
        """Test updating notes on a history entry."""
        item = queue_with_items["items"][0]
        room_id = queue_with_items["room"]["_id"]

        history = await history_service.mark_as_watched(WatchHistoryCreate(
            room_id=room_id,
            item_id=item.id,
        ))

        history = await history_service.update_notes(
            history.id,
            "Bob fell asleep halfway through",
        )

        assert history.notes == "Bob fell asleep halfway through"

    async def test_get_stats(
        self,
        history_service: HistoryService,
        queue_with_items: dict,
    ):
        """Test getting watch statistics."""
        room_id = queue_with_items["room"]["_id"]
        items = queue_with_items["items"]

        # Watch 3 items with ratings
        for i, item in enumerate(items[:3]):
            history = await history_service.mark_as_watched(WatchHistoryCreate(
                room_id=room_id,
                item_id=item.id,
            ))
            await history_service.add_rating(history.id, "alice", 3 + i)
            await history_service.add_rating(history.id, "bob", 4)

        stats = await history_service.get_stats(room_id)

        assert stats["total_watched"] == 3
        assert stats["total_ratings"] == 6
        assert 3.0 <= stats["avg_rating"] <= 4.5

    async def test_get_history_for_item(
        self,
        history_service: HistoryService,
        queue_with_items: dict,
    ):
        """Test getting history entry for a specific item."""
        item = queue_with_items["items"][0]
        room_id = queue_with_items["room"]["_id"]

        created = await history_service.mark_as_watched(WatchHistoryCreate(
            room_id=room_id,
            item_id=item.id,
        ))

        history = await history_service.get_history_for_item(item.id)

        assert history is not None
        assert history.id == created.id


class TestHistoryAPI:
    """Tests for history API endpoints."""

    async def test_rate_watched_item_api(
        self,
        client: AsyncClient,
        history_service: HistoryService,
        queue_with_items: dict,
    ):
        """Test POST /api/votes/history/{history_id}/rate endpoint."""
        item = queue_with_items["items"][0]
        room_id = queue_with_items["room"]["_id"]

        history = await history_service.mark_as_watched(WatchHistoryCreate(
            room_id=room_id,
            item_id=item.id,
        ))

        response = await client.post(
            f"/api/votes/history/{history.id}/rate",
            json={"user_id": "alice", "rating": 5},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ratings"]["alice"] == 5

    async def test_get_room_history_api(
        self,
        client: AsyncClient,
        history_service: HistoryService,
        queue_with_items: dict,
    ):
        """Test GET /api/votes/history/room/{room_id} endpoint."""
        room_id = queue_with_items["room"]["_id"]
        items = queue_with_items["items"]

        for item in items[:2]:
            await history_service.mark_as_watched(WatchHistoryCreate(
                room_id=room_id,
                item_id=item.id,
            ))

        response = await client.get(f"/api/votes/history/room/{room_id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_get_history_stats_api(
        self,
        client: AsyncClient,
        history_service: HistoryService,
        queue_with_items: dict,
    ):
        """Test GET /api/votes/history/room/{room_id}/stats endpoint."""
        room_id = queue_with_items["room"]["_id"]
        items = queue_with_items["items"]

        history = await history_service.mark_as_watched(WatchHistoryCreate(
            room_id=room_id,
            item_id=items[0].id,
        ))
        await history_service.add_rating(history.id, "alice", 5)

        response = await client.get(f"/api/votes/history/room/{room_id}/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_watched"] == 1
        assert data["avg_rating"] == 5.0

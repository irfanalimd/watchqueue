"""Tests for queue management."""

import asyncio
import pytest
from httpx import AsyncClient

from app.models.queue_item import QueueItemCreate, QueueItemUpdate, QueueItemStatus
from app.services.queue import QueueService


class TestQueueService:
    """Tests for QueueService."""

    async def test_add_item_to_queue(
        self,
        queue_service: QueueService,
        movie_room: dict,
    ):
        """Test adding an item to the queue."""
        item = await queue_service.add_item(QueueItemCreate(
            room_id=movie_room["_id"],
            title="Inception",
            added_by="alice",
        ))

        assert item.title == "Inception"
        assert item.added_by == "alice"
        assert item.room_id == movie_room["_id"]
        assert item.status == QueueItemStatus.QUEUED
        assert item.vote_score == 0

    async def test_add_item_with_tmdb_id(
        self,
        queue_service: QueueService,
        movie_room: dict,
    ):
        """Test adding an item with TMDB ID."""
        item = await queue_service.add_item(QueueItemCreate(
            room_id=movie_room["_id"],
            title="The Matrix",
            added_by="bob",
            tmdb_id=603,
        ))

        assert item.title == "The Matrix"
        assert item.tmdb_id == 603

    async def test_duplicate_prevention_by_title(
        self,
        queue_service: QueueService,
        movie_room: dict,
    ):
        """Test that duplicate items (by title) are prevented."""
        item1 = await queue_service.add_item(QueueItemCreate(
            room_id=movie_room["_id"],
            title="Inception",
            added_by="alice",
        ))

        # Try to add same movie with different case
        item2 = await queue_service.add_item(QueueItemCreate(
            room_id=movie_room["_id"],
            title="INCEPTION",
            added_by="bob",
        ))

        # Should return the same item
        assert item1.id == item2.id
        assert item2.added_by == "alice"  # Original adder preserved

    async def test_concurrent_duplicate_adds(
        self,
        queue_service: QueueService,
        movie_room: dict,
    ):
        """Test that concurrent adds of same movie result in single item."""
        async def add_movie(user: str):
            return await queue_service.add_item(QueueItemCreate(
                room_id=movie_room["_id"],
                title="Interstellar",
                added_by=user,
            ))

        # Simulate concurrent adds
        results = await asyncio.gather(
            add_movie("alice"),
            add_movie("bob"),
            add_movie("charlie"),
            add_movie("diana"),
        )

        # All should return the same item ID
        item_ids = set(r.id for r in results)
        assert len(item_ids) == 1, "Concurrent adds should result in single item"

    async def test_get_room_queue(
        self,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test getting all items in a room's queue."""
        room_id = queue_with_items["room"]["_id"]
        items = await queue_service.get_room_queue(room_id)

        assert len(items) == 5
        # Should be sorted by vote_score (all 0) then by added_at
        assert items[0].title == "Inception"

    async def test_get_room_queue_by_status(
        self,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test filtering queue by status."""
        room_id = queue_with_items["room"]["_id"]
        items = queue_with_items["items"]

        # Mark one as watched
        await queue_service.mark_watched(items[0].id)

        queued = await queue_service.get_room_queue(
            room_id,
            status=QueueItemStatus.QUEUED,
        )
        assert len(queued) == 4

        watched = await queue_service.get_room_queue(
            room_id,
            status=QueueItemStatus.WATCHED,
        )
        assert len(watched) == 1

    async def test_update_item(
        self,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test updating a queue item."""
        item = queue_with_items["items"][0]

        updated = await queue_service.update_item(
            item.id,
            QueueItemUpdate(
                poster_url="https://example.com/poster.jpg",
                year=2010,
                genres=["Sci-Fi", "Action"],
            ),
        )

        assert updated is not None
        assert updated.poster_url == "https://example.com/poster.jpg"
        assert updated.year == 2010
        assert updated.genres == ["Sci-Fi", "Action"]

    async def test_enrich_item(
        self,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test enriching an item with metadata."""
        item = queue_with_items["items"][0]

        enriched = await queue_service.enrich_item(
            item.id,
            poster_url="https://image.tmdb.org/poster.jpg",
            year=2010,
            runtime_minutes=148,
            genres=["Sci-Fi", "Action", "Thriller"],
            streaming_on=["Netflix", "Amazon Prime"],
            play_now_url="https://www.themoviedb.org/movie/27205/watch",
            provider_links=[
                {
                    "provider_name": "Netflix",
                    "region": "US",
                    "access_type": "flatrate",
                    "provider_logo": "https://image.tmdb.org/t/p/w500/logo.png",
                    "link": "https://www.themoviedb.org/movie/27205/watch",
                }
            ],
            providers_by_region={"US": ["Netflix", "Amazon Prime"]},
            tmdb_id=27205,
        )

        assert enriched is not None
        assert enriched.tmdb_id == 27205
        assert enriched.runtime_minutes == 148
        assert "Netflix" in enriched.streaming_on
        assert enriched.play_now_url is not None
        assert enriched.provider_links[0].provider_name == "Netflix"

    async def test_remove_item(
        self,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test removing an item (soft delete)."""
        item = queue_with_items["items"][0]
        room_id = queue_with_items["room"]["_id"]

        removed = await queue_service.remove_item(item.id)
        assert removed is True

        # Item should not appear in queue
        items = await queue_service.get_room_queue(room_id)
        assert len(items) == 4
        assert not any(i.id == item.id for i in items)

        # But item should still exist with removed status
        removed_item = await queue_service.get_item(item.id)
        assert removed_item is not None
        assert removed_item.status == QueueItemStatus.REMOVED

    async def test_mark_watching(
        self,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test marking an item as currently being watched."""
        item = queue_with_items["items"][0]

        updated = await queue_service.mark_watching(item.id)

        assert updated is not None
        assert updated.status == QueueItemStatus.WATCHING

    async def test_update_vote_counts(
        self,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test updating vote counts."""
        item = queue_with_items["items"][0]

        updated = await queue_service.update_vote_counts(
            item.id,
            upvotes=5,
            downvotes=2,
        )

        assert updated is not None
        assert updated.upvotes == 5
        assert updated.downvotes == 2
        assert updated.vote_score == 3

    async def test_get_top_items(
        self,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test getting top voted items."""
        room_id = queue_with_items["room"]["_id"]
        items = queue_with_items["items"]

        # Set different vote scores
        await queue_service.update_vote_counts(items[0].id, upvotes=5, downvotes=0)
        await queue_service.update_vote_counts(items[1].id, upvotes=3, downvotes=1)
        await queue_service.update_vote_counts(items[2].id, upvotes=10, downvotes=2)

        top = await queue_service.get_top_items(room_id, limit=3)

        assert len(top) == 3
        assert top[0].id == items[2].id  # Interstellar (score 8)
        assert top[1].id == items[0].id  # Inception (score 5)
        assert top[2].id == items[1].id  # The Matrix (score 2)


class TestQueueAPI:
    """Tests for queue API endpoints."""

    async def test_add_to_queue_api(
        self,
        client: AsyncClient,
        movie_room: dict,
    ):
        """Test POST /api/queue endpoint."""
        response = await client.post(
            "/api/queue",
            json={
                "room_id": movie_room["_id"],
                "title": "The Shawshank Redemption",
                "added_by": "alice",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "The Shawshank Redemption"
        assert data["status"] == "queued"

    async def test_get_room_queue_api(
        self,
        client: AsyncClient,
        queue_with_items: dict,
    ):
        """Test GET /api/queue/room/{room_id} endpoint."""
        room_id = queue_with_items["room"]["_id"]
        response = await client.get(f"/api/queue/room/{room_id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

    async def test_get_room_queue_with_provider_filter_api(
        self,
        client: AsyncClient,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Provider filter returns matching items only."""
        room_id = queue_with_items["room"]["_id"]
        first_item = queue_with_items["items"][0]
        await queue_service.enrich_item(
            first_item.id,
            streaming_on=["Netflix"],
            providers_by_region={"US": ["Netflix"]},
            provider_links=[],
        )

        response = await client.get(f"/api/queue/room/{room_id}?provider=Netflix")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["_id"] == first_item.id

    async def test_get_room_queue_available_now_filter_api(
        self,
        client: AsyncClient,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Available-now filter only returns streamable items."""
        room_id = queue_with_items["room"]["_id"]
        first_item = queue_with_items["items"][0]
        await queue_service.enrich_item(
            first_item.id,
            streaming_on=["Netflix"],
            providers_by_region={"US": ["Netflix"]},
            provider_links=[],
        )

        response = await client.get(f"/api/queue/room/{room_id}?available_now=true")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["_id"] == first_item.id

    async def test_get_queue_item_api(
        self,
        client: AsyncClient,
        queue_with_items: dict,
    ):
        """Test GET /api/queue/{item_id} endpoint."""
        item = queue_with_items["items"][0]
        response = await client.get(f"/api/queue/{item.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == item.title

    async def test_update_queue_item_api(
        self,
        client: AsyncClient,
        queue_with_items: dict,
    ):
        """Test PATCH /api/queue/{item_id} endpoint."""
        item = queue_with_items["items"][0]
        response = await client.patch(
            f"/api/queue/{item.id}",
            json={"year": 2010, "genres": ["Sci-Fi"]},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["year"] == 2010
        assert data["genres"] == ["Sci-Fi"]

    async def test_remove_from_queue_api(
        self,
        client: AsyncClient,
        queue_with_items: dict,
    ):
        """Test DELETE /api/queue/{item_id} endpoint."""
        item = queue_with_items["items"][0]
        response = await client.delete(f"/api/queue/{item.id}")

        assert response.status_code == 204

    async def test_select_next_api(
        self,
        client: AsyncClient,
        queue_with_items: dict,
    ):
        """Test POST /api/queue/room/{room_id}/select endpoint."""
        room_id = queue_with_items["room"]["_id"]
        response = await client.post(f"/api/queue/room/{room_id}/select")

        assert response.status_code == 200
        data = response.json()
        assert "title" in data
        assert data["status"] == "queued"

"""Tests for voting with atomic operations and concurrent access."""

import asyncio
import pytest
from httpx import AsyncClient

from app.models.vote import VoteCreate, VoteType
from app.services.voting import VotingService
from app.services.queue import QueueService


class TestVotingService:
    """Tests for VotingService with atomic operations."""

    async def test_cast_vote(
        self,
        voting_service: VotingService,
        queue_with_items: dict,
    ):
        """Test casting a vote."""
        item = queue_with_items["items"][0]

        vote = await voting_service.vote(VoteCreate(
            item_id=item.id,
            user_id="alice",
            vote=VoteType.UP,
        ))

        assert vote.item_id == item.id
        assert vote.user_id == "alice"
        assert vote.vote == VoteType.UP

    async def test_vote_updates_counts(
        self,
        voting_service: VotingService,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test that voting updates denormalized counts."""
        item = queue_with_items["items"][0]

        await voting_service.vote(VoteCreate(
            item_id=item.id,
            user_id="alice",
            vote=VoteType.UP,
        ))

        updated_item = await queue_service.get_item(item.id)
        assert updated_item.upvotes == 1
        assert updated_item.downvotes == 0
        assert updated_item.vote_score == 1

    async def test_change_vote(
        self,
        voting_service: VotingService,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test changing a vote from up to down."""
        item = queue_with_items["items"][0]

        # Vote up
        await voting_service.vote(VoteCreate(
            item_id=item.id,
            user_id="alice",
            vote=VoteType.UP,
        ))

        # Change to down
        vote = await voting_service.vote(VoteCreate(
            item_id=item.id,
            user_id="alice",
            vote=VoteType.DOWN,
        ))

        assert vote.vote == VoteType.DOWN

        # Check counts updated correctly
        updated_item = await queue_service.get_item(item.id)
        assert updated_item.upvotes == 0
        assert updated_item.downvotes == 1
        assert updated_item.vote_score == -1

    async def test_concurrent_votes_atomic(
        self,
        voting_service: VotingService,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test that concurrent votes are handled atomically.

        All 4 users vote simultaneously; verify final count is correct.
        """
        item = queue_with_items["items"][0]

        # All 4 users vote simultaneously
        await asyncio.gather(
            voting_service.vote(VoteCreate(item_id=item.id, user_id="alice", vote=VoteType.UP)),
            voting_service.vote(VoteCreate(item_id=item.id, user_id="bob", vote=VoteType.UP)),
            voting_service.vote(VoteCreate(item_id=item.id, user_id="charlie", vote=VoteType.DOWN)),
            voting_service.vote(VoteCreate(item_id=item.id, user_id="diana", vote=VoteType.UP)),
        )

        updated_item = await queue_service.get_item(item.id)
        assert updated_item.upvotes == 3
        assert updated_item.downvotes == 1
        assert updated_item.vote_score == 2

    async def test_concurrent_vote_changes(
        self,
        voting_service: VotingService,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test concurrent vote changes are handled correctly."""
        item = queue_with_items["items"][0]

        # Initial votes
        await asyncio.gather(
            voting_service.vote(VoteCreate(item_id=item.id, user_id="alice", vote=VoteType.UP)),
            voting_service.vote(VoteCreate(item_id=item.id, user_id="bob", vote=VoteType.UP)),
            voting_service.vote(VoteCreate(item_id=item.id, user_id="charlie", vote=VoteType.UP)),
            voting_service.vote(VoteCreate(item_id=item.id, user_id="diana", vote=VoteType.UP)),
        )

        # All change their votes simultaneously
        await asyncio.gather(
            voting_service.vote(VoteCreate(item_id=item.id, user_id="alice", vote=VoteType.DOWN)),
            voting_service.vote(VoteCreate(item_id=item.id, user_id="bob", vote=VoteType.DOWN)),
            voting_service.vote(VoteCreate(item_id=item.id, user_id="charlie", vote=VoteType.DOWN)),
            voting_service.vote(VoteCreate(item_id=item.id, user_id="diana", vote=VoteType.DOWN)),
        )

        updated_item = await queue_service.get_item(item.id)
        assert updated_item.upvotes == 0
        assert updated_item.downvotes == 4
        assert updated_item.vote_score == -4

    async def test_remove_vote(
        self,
        voting_service: VotingService,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test removing a vote."""
        item = queue_with_items["items"][0]

        await voting_service.vote(VoteCreate(
            item_id=item.id,
            user_id="alice",
            vote=VoteType.UP,
        ))

        removed = await voting_service.remove_vote(item.id, "alice")
        assert removed is True

        updated_item = await queue_service.get_item(item.id)
        assert updated_item.upvotes == 0
        assert updated_item.vote_score == 0

    async def test_get_vote(
        self,
        voting_service: VotingService,
        queue_with_items: dict,
    ):
        """Test getting a user's vote."""
        item = queue_with_items["items"][0]

        await voting_service.vote(VoteCreate(
            item_id=item.id,
            user_id="alice",
            vote=VoteType.UP,
        ))

        vote = await voting_service.get_vote(item.id, "alice")
        assert vote is not None
        assert vote.vote == VoteType.UP

        # Non-existent vote
        no_vote = await voting_service.get_vote(item.id, "unknown")
        assert no_vote is None

    async def test_get_item_votes(
        self,
        voting_service: VotingService,
        queue_with_items: dict,
    ):
        """Test getting all votes for an item."""
        item = queue_with_items["items"][0]

        await asyncio.gather(
            voting_service.vote(VoteCreate(item_id=item.id, user_id="alice", vote=VoteType.UP)),
            voting_service.vote(VoteCreate(item_id=item.id, user_id="bob", vote=VoteType.DOWN)),
        )

        votes = await voting_service.get_item_votes(item.id)
        assert len(votes) == 2

        vote_by_user = {v.user_id: v.vote for v in votes}
        assert vote_by_user["alice"] == VoteType.UP
        assert vote_by_user["bob"] == VoteType.DOWN

    async def test_get_user_votes_in_room(
        self,
        voting_service: VotingService,
        queue_with_items: dict,
    ):
        """Test getting all of a user's votes in a room."""
        room_id = queue_with_items["room"]["_id"]
        items = queue_with_items["items"]

        # Alice votes on multiple items
        await asyncio.gather(
            voting_service.vote(VoteCreate(item_id=items[0].id, user_id="alice", vote=VoteType.UP)),
            voting_service.vote(VoteCreate(item_id=items[1].id, user_id="alice", vote=VoteType.DOWN)),
            voting_service.vote(VoteCreate(item_id=items[2].id, user_id="alice", vote=VoteType.UP)),
        )

        votes = await voting_service.get_user_votes_in_room(room_id, "alice")
        assert len(votes) == 3
        assert votes[items[0].id] == VoteType.UP
        assert votes[items[1].id] == VoteType.DOWN
        assert votes[items[2].id] == VoteType.UP

    async def test_vote_invalid_item(
        self,
        voting_service: VotingService,
    ):
        """Test voting on non-existent item."""
        with pytest.raises(ValueError, match="Item not found"):
            await voting_service.vote(VoteCreate(
                item_id="000000000000000000000000",
                user_id="alice",
                vote=VoteType.UP,
            ))

    async def test_vote_prevents_duplicates(
        self,
        voting_service: VotingService,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test that duplicate votes from same user are prevented."""
        item = queue_with_items["items"][0]

        # Vote twice with same value
        await voting_service.vote(VoteCreate(
            item_id=item.id,
            user_id="alice",
            vote=VoteType.UP,
        ))
        await voting_service.vote(VoteCreate(
            item_id=item.id,
            user_id="alice",
            vote=VoteType.UP,
        ))

        # Should still only be 1 upvote
        updated_item = await queue_service.get_item(item.id)
        assert updated_item.upvotes == 1


class TestVotingAPI:
    """Tests for voting API endpoints."""

    async def test_cast_vote_api(
        self,
        client: AsyncClient,
        queue_with_items: dict,
    ):
        """Test POST /api/votes endpoint."""
        item = queue_with_items["items"][0]

        response = await client.post(
            "/api/votes",
            json={
                "item_id": item.id,
                "user_id": "alice",
                "vote": "up",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["vote"] == "up"

    async def test_get_vote_api(
        self,
        client: AsyncClient,
        voting_service: VotingService,
        queue_with_items: dict,
    ):
        """Test GET /api/votes/{item_id}/{user_id} endpoint."""
        item = queue_with_items["items"][0]

        await voting_service.vote(VoteCreate(
            item_id=item.id,
            user_id="alice",
            vote=VoteType.UP,
        ))

        response = await client.get(f"/api/votes/{item.id}/alice")
        assert response.status_code == 200
        data = response.json()
        assert data["vote"] == "up"

    async def test_get_item_votes_api(
        self,
        client: AsyncClient,
        voting_service: VotingService,
        queue_with_items: dict,
    ):
        """Test GET /api/votes/item/{item_id} endpoint."""
        item = queue_with_items["items"][0]

        await voting_service.vote(VoteCreate(item_id=item.id, user_id="alice", vote=VoteType.UP))
        await voting_service.vote(VoteCreate(item_id=item.id, user_id="bob", vote=VoteType.DOWN))

        response = await client.get(f"/api/votes/item/{item.id}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_get_vote_counts_api(
        self,
        client: AsyncClient,
        voting_service: VotingService,
        queue_with_items: dict,
    ):
        """Test GET /api/votes/item/{item_id}/counts endpoint."""
        item = queue_with_items["items"][0]

        await voting_service.vote(VoteCreate(item_id=item.id, user_id="alice", vote=VoteType.UP))
        await voting_service.vote(VoteCreate(item_id=item.id, user_id="bob", vote=VoteType.UP))
        await voting_service.vote(VoteCreate(item_id=item.id, user_id="charlie", vote=VoteType.DOWN))

        response = await client.get(f"/api/votes/item/{item.id}/counts")
        assert response.status_code == 200
        data = response.json()
        assert data["upvotes"] == 2
        assert data["downvotes"] == 1
        assert data["vote_score"] == 1

    async def test_remove_vote_api(
        self,
        client: AsyncClient,
        voting_service: VotingService,
        queue_with_items: dict,
    ):
        """Test DELETE /api/votes/{item_id}/{user_id} endpoint."""
        item = queue_with_items["items"][0]

        await voting_service.vote(VoteCreate(
            item_id=item.id,
            user_id="alice",
            vote=VoteType.UP,
        ))

        response = await client.delete(f"/api/votes/{item.id}/alice")
        assert response.status_code == 204

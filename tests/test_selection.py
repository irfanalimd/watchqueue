"""Tests for selection algorithms and fairness."""

import asyncio
from collections import Counter
import pytest

from app.models.room import SelectionMode
from app.models.vote import VoteCreate, VoteType
from app.models.watch_history import WatchHistoryCreate
from app.services.selection import SelectionService
from app.services.queue import QueueService
from app.services.voting import VotingService
from app.services.history import HistoryService


class TestSelectionService:
    """Tests for SelectionService algorithms."""

    async def test_select_highest_votes(
        self,
        selection_service: SelectionService,
        voting_service: VotingService,
        queue_with_items: dict,
    ):
        """Test highest votes selection mode."""
        room_id = queue_with_items["room"]["_id"]
        items = queue_with_items["items"]

        # Give different vote counts
        await voting_service.vote(VoteCreate(item_id=items[0].id, user_id="alice", vote=VoteType.UP))
        await voting_service.vote(VoteCreate(item_id=items[0].id, user_id="bob", vote=VoteType.UP))

        await voting_service.vote(VoteCreate(item_id=items[2].id, user_id="alice", vote=VoteType.UP))
        await voting_service.vote(VoteCreate(item_id=items[2].id, user_id="bob", vote=VoteType.UP))
        await voting_service.vote(VoteCreate(item_id=items[2].id, user_id="charlie", vote=VoteType.UP))

        # Interstellar should win with 3 votes
        selected = await selection_service.select_next(
            room_id,
            mode=SelectionMode.HIGHEST_VOTES,
        )

        assert selected is not None
        assert selected.id == items[2].id
        assert selected.title == "Interstellar"

    async def test_select_highest_votes_tie_breaker(
        self,
        selection_service: SelectionService,
        queue_with_items: dict,
    ):
        """Test tie-breaking by added_at when votes are equal."""
        room_id = queue_with_items["room"]["_id"]
        items = queue_with_items["items"]

        # All have 0 votes, should pick first added
        selected = await selection_service.select_next(
            room_id,
            mode=SelectionMode.HIGHEST_VOTES,
        )

        assert selected is not None
        assert selected.id == items[0].id  # Inception was added first

    async def test_select_weighted_random(
        self,
        selection_service: SelectionService,
        voting_service: VotingService,
        queue_with_items: dict,
    ):
        """Test weighted random selection."""
        room_id = queue_with_items["room"]["_id"]
        items = queue_with_items["items"]

        # Give one item many votes
        for user in ["alice", "bob", "charlie", "diana"]:
            await voting_service.vote(VoteCreate(
                item_id=items[0].id,
                user_id=user,
                vote=VoteType.UP,
            ))

        # Run selection multiple times
        selections = Counter()
        for _ in range(100):
            selected = await selection_service.select_next(
                room_id,
                mode=SelectionMode.WEIGHTED_RANDOM,
            )
            if selected:
                selections[selected.id] += 1

        # Item with most votes should be selected most often
        assert selections[items[0].id] > selections.get(items[1].id, 0)

    async def test_fair_selection_distribution(
        self,
        selection_service: SelectionService,
        queue_with_items: dict,
    ):
        """Test that weighted random doesn't always pick the same item.

        Run 100 selections; verify no single item dominates completely.
        """
        room_id = queue_with_items["room"]["_id"]

        selections = Counter()
        for _ in range(100):
            selected = await selection_service.select_next(
                room_id,
                mode=SelectionMode.WEIGHTED_RANDOM,
            )
            if selected:
                selections[selected.id] += 1

        # All items should have equal chance when no votes
        # At least 3 different items should be selected
        assert len(selections) >= 3, "Selection should have variety"

        # No single item should have more than 50% of selections
        max_selections = max(selections.values())
        assert max_selections < 50, "No item should dominate selections"

    async def test_select_round_robin(
        self,
        selection_service: SelectionService,
        history_service: HistoryService,
        queue_service: QueueService,
        queue_with_items: dict,
    ):
        """Test round robin selection rotates through users."""
        room_id = queue_with_items["room"]["_id"]
        items = queue_with_items["items"]

        # Mark first item as watched (added by alice)
        await history_service.mark_as_watched(WatchHistoryCreate(
            room_id=room_id,
            item_id=items[0].id,
        ))

        # Next selection should favor users who haven't had picks
        selected = await selection_service.select_next(
            room_id,
            mode=SelectionMode.ROUND_ROBIN,
        )

        assert selected is not None
        # Should pick from bob, charlie, or diana (not alice again)
        assert selected.added_by != "alice"

    async def test_select_with_timeout(
        self,
        selection_service: SelectionService,
        queue_with_items: dict,
    ):
        """Test selection respects timeout."""
        room_id = queue_with_items["room"]["_id"]

        # Short timeout should still work
        selected = await selection_service.select_next(
            room_id,
            timeout=5.0,
        )

        assert selected is not None

    async def test_select_empty_queue(
        self,
        selection_service: SelectionService,
        movie_room: dict,
    ):
        """Test selection on empty queue returns None."""
        selected = await selection_service.select_next(movie_room["_id"])
        assert selected is None

    async def test_start_voting_round(
        self,
        selection_service: SelectionService,
        movie_room: dict,
    ):
        """Test starting a voting round."""
        round_info = await selection_service.start_voting_round(
            movie_room["_id"],
            duration_seconds=30,
        )

        assert round_info["room_id"] == movie_room["_id"]
        assert round_info["duration_seconds"] == 30
        assert round_info["status"] == "voting"
        assert "start_time" in round_info

    async def test_get_selection_stats(
        self,
        selection_service: SelectionService,
        history_service: HistoryService,
        queue_with_items: dict,
    ):
        """Test getting selection statistics."""
        room_id = queue_with_items["room"]["_id"]
        items = queue_with_items["items"]

        # Mark some items as watched
        await history_service.mark_as_watched(WatchHistoryCreate(
            room_id=room_id,
            item_id=items[0].id,  # Alice's pick
        ))
        await history_service.mark_as_watched(WatchHistoryCreate(
            room_id=room_id,
            item_id=items[4].id,  # Also Alice's pick
        ))
        await history_service.mark_as_watched(WatchHistoryCreate(
            room_id=room_id,
            item_id=items[1].id,  # Bob's pick
        ))

        stats = await selection_service.get_selection_stats(room_id)

        assert stats["total_watched"] == 3
        assert "user_stats" in stats
        assert stats["user_stats"]["alice"]["items_picked"] == 2
        assert stats["user_stats"]["bob"]["items_picked"] == 1


class TestSelectionFairness:
    """Statistical tests for selection fairness."""

    async def test_no_user_statistically_favored(
        self,
        selection_service: SelectionService,
        queue_with_items: dict,
    ):
        """Run 100 selections; verify no user's picks are statistically favored."""
        room_id = queue_with_items["room"]["_id"]
        items = queue_with_items["items"]

        # Map items to who added them
        adder_by_item = {item.id: item.added_by for item in items}

        selections_by_user = Counter()
        for _ in range(100):
            selected = await selection_service.select_next(
                room_id,
                mode=SelectionMode.WEIGHTED_RANDOM,
            )
            if selected:
                adder = adder_by_item[selected.id]
                selections_by_user[adder] += 1

        # With 5 items:
        # - alice added 2 items (should get ~40% of selections)
        # - bob, charlie, diana added 1 each (should get ~20% each)

        # Check that alice (with 2 items) gets roughly 2x the selections
        alice_ratio = selections_by_user["alice"] / 100
        single_item_avg = sum(
            selections_by_user[u] for u in ["bob", "charlie", "diana"]
        ) / 3 / 100

        # Alice should have between 1.5x and 2.5x the average single-item user
        assert 0.15 <= single_item_avg <= 0.35, f"Single item users should average ~20%"
        assert 0.25 <= alice_ratio <= 0.55, f"Alice (2 items) should get ~40%"

    async def test_negative_votes_still_get_picked(
        self,
        selection_service: SelectionService,
        voting_service: VotingService,
        queue_with_items: dict,
    ):
        """Test that items with negative votes can still be picked."""
        room_id = queue_with_items["room"]["_id"]
        items = queue_with_items["items"]

        # Give one item negative votes
        await voting_service.vote(VoteCreate(
            item_id=items[0].id,
            user_id="alice",
            vote=VoteType.DOWN,
        ))

        # Give another very positive votes
        for user in ["alice", "bob", "charlie", "diana"]:
            await voting_service.vote(VoteCreate(
                item_id=items[1].id,
                user_id=user,
                vote=VoteType.UP,
            ))

        # Negative item should still sometimes be picked
        picked_negative = False
        for _ in range(50):
            selected = await selection_service.select_next(
                room_id,
                mode=SelectionMode.WEIGHTED_RANDOM,
            )
            if selected and selected.id == items[0].id:
                picked_negative = True
                break

        assert picked_negative, "Negative voted items should still have a chance"

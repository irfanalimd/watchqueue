"""Selection service for fair movie/show picking algorithms."""

import asyncio
import random
from collections import defaultdict
from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.room import SelectionMode
from app.models.queue_item import QueueItem, QueueItemStatus


class SelectionService:
    """Service for fair selection of what to watch next.

    Implements multiple selection algorithms:
    - weighted_random: Higher voted items have better chances but not guaranteed
    - highest_votes: Simply picks the item with most votes
    - round_robin: Rotates through users who added items fairly
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.queue_collection = db.queue_items
        self.history_collection = db.watch_history
        self.rooms_collection = db.rooms

    async def select_next(
        self,
        room_id: str,
        mode: SelectionMode | None = None,
        timeout: float = 30.0,
    ) -> QueueItem | None:
        """Select the next item to watch based on selection mode.

        Args:
            room_id: The room to select for
            mode: Override selection mode (uses room settings if None)
            timeout: Maximum time to wait for selection

        Returns:
            Selected queue item or None if queue is empty
        """
        if not ObjectId.is_valid(room_id):
            return None

        room_oid = ObjectId(room_id)

        # Get room settings if mode not specified
        if mode is None:
            room = await self.rooms_collection.find_one({"_id": room_oid})
            if not room:
                return None
            mode = SelectionMode(room["settings"]["selection_mode"])

        try:
            result = await asyncio.wait_for(
                self._do_selection(room_oid, mode),
                timeout=timeout,
            )
            return result
        except asyncio.TimeoutError:
            # Fallback to highest votes on timeout
            return await self._select_highest_votes(room_oid)

    async def _do_selection(
        self,
        room_id: ObjectId,
        mode: SelectionMode,
    ) -> QueueItem | None:
        """Perform selection based on mode."""
        if mode == SelectionMode.HIGHEST_VOTES:
            return await self._select_highest_votes(room_id)
        elif mode == SelectionMode.ROUND_ROBIN:
            return await self._select_round_robin(room_id)
        else:  # WEIGHTED_RANDOM
            return await self._select_weighted_random(room_id)

    async def _select_highest_votes(self, room_id: ObjectId) -> QueueItem | None:
        """Select the item with the highest vote score."""
        item = await self.queue_collection.find_one(
            {
                "room_id": room_id,
                "status": QueueItemStatus.QUEUED.value,
            },
            sort=[("vote_score", -1), ("added_at", 1)],
        )

        if item:
            item["_id"] = str(item["_id"])
            item["room_id"] = str(item["room_id"])
            return QueueItem(**item)
        return None

    async def _select_weighted_random(self, room_id: ObjectId) -> QueueItem | None:
        """Select randomly with weights based on vote scores.

        Uses a scoring system where:
        - Base weight = 1 (everyone has a chance)
        - Additional weight = max(0, vote_score) * 2
        - This ensures negative scored items can still be picked occasionally
        """
        items = []
        async for item in self.queue_collection.find({
            "room_id": room_id,
            "status": QueueItemStatus.QUEUED.value,
        }):
            items.append(item)

        if not items:
            return None

        # Calculate weights
        weights = []
        for item in items:
            vote_score = item.get("vote_score", 0)
            # Base weight of 1 + bonus for positive votes
            weight = 1 + max(0, vote_score) * 2
            weights.append(weight)

        # Weighted random selection
        selected = random.choices(items, weights=weights, k=1)[0]
        selected["_id"] = str(selected["_id"])
        selected["room_id"] = str(selected["room_id"])
        return QueueItem(**selected)

    async def _select_round_robin(self, room_id: ObjectId) -> QueueItem | None:
        """Select fairly by rotating through users who added items.

        Tracks which users have had their picks watched recently
        and prioritizes users who haven't had a turn in a while.
        """
        # Get recent watch history to see who's had picks
        recent_history = []
        async for entry in self.history_collection.find(
            {"room_id": room_id}
        ).sort("watched_at", -1).limit(50):
            recent_history.append(entry)

        # Get all queued items grouped by who added them
        items_by_user: dict[str, list[dict]] = defaultdict(list)
        async for item in self.queue_collection.find({
            "room_id": room_id,
            "status": QueueItemStatus.QUEUED.value,
        }):
            items_by_user[item["added_by"]].append(item)

        if not items_by_user:
            return None

        # Build a priority list of users (least recently picked first)
        recent_pickers = []
        for entry in recent_history:
            item = await self.queue_collection.find_one({"_id": entry["item_id"]})
            if item:
                recent_pickers.append(item["added_by"])

        # Users with items in queue
        users_with_items = list(items_by_user.keys())

        # Sort by least recent pick (users not in recent_pickers go first)
        def user_priority(user: str) -> int:
            try:
                return recent_pickers.index(user)
            except ValueError:
                return -1  # Never picked = highest priority

        users_with_items.sort(key=user_priority)

        # Pick from the highest priority user's items (highest voted)
        priority_user = users_with_items[0]
        user_items = sorted(
            items_by_user[priority_user],
            key=lambda x: x.get("vote_score", 0),
            reverse=True,
        )

        selected = user_items[0]
        selected["_id"] = str(selected["_id"])
        selected["room_id"] = str(selected["room_id"])
        return QueueItem(**selected)

    async def start_voting_round(
        self,
        room_id: str,
        duration_seconds: int | None = None,
    ) -> dict:
        """Start a timed voting round.

        Returns info about the voting round that clients can use
        to display a countdown timer.
        """
        if not ObjectId.is_valid(room_id):
            raise ValueError("Invalid room_id")

        room_oid = ObjectId(room_id)

        # Get room settings for default duration
        if duration_seconds is None:
            room = await self.rooms_collection.find_one({"_id": room_oid})
            if not room:
                raise ValueError("Room not found")
            duration_seconds = room["settings"]["voting_duration_seconds"]

        start_time = datetime.utcnow()

        return {
            "room_id": room_id,
            "start_time": start_time.isoformat(),
            "duration_seconds": duration_seconds,
            "status": "voting",
        }

    async def get_selection_stats(self, room_id: str) -> dict:
        """Get statistics about selection fairness in a room."""
        if not ObjectId.is_valid(room_id):
            return {}

        room_oid = ObjectId(room_id)

        # Count picks by user
        picks_by_user: dict[str, int] = defaultdict(int)

        async for entry in self.history_collection.find({"room_id": room_oid}):
            item = await self.queue_collection.find_one({"_id": entry["item_id"]})
            if item:
                picks_by_user[item["added_by"]] += 1

        # Count items added by user
        items_by_user: dict[str, int] = defaultdict(int)
        async for item in self.queue_collection.find({"room_id": room_oid}):
            items_by_user[item["added_by"]] += 1

        # Calculate pick rates
        user_stats = {}
        for user in set(list(picks_by_user.keys()) + list(items_by_user.keys())):
            added = items_by_user.get(user, 0)
            picked = picks_by_user.get(user, 0)
            rate = picked / added if added > 0 else 0.0
            user_stats[user] = {
                "items_added": added,
                "items_picked": picked,
                "pick_rate": round(rate, 2),
            }

        return {
            "total_watched": sum(picks_by_user.values()),
            "user_stats": user_stats,
        }

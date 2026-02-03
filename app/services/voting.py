"""Voting service with atomic operations for concurrent vote handling."""

from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.models.vote import Vote, VoteCreate, VoteType


class VotingService:
    """Service for managing votes with atomic operations.

    Uses top-level item_id + user_id fields with a unique compound index
    to prevent duplicate votes and ensure atomic vote operations.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.votes_collection = db.votes
        self.queue_collection = db.queue_items

    async def vote(self, vote_data: VoteCreate) -> Vote:
        """Cast or update a vote.

        Uses upsert with unique compound index to atomically handle:
        - New votes
        - Vote changes (up to down, down to up)
        - Prevents duplicate votes from same user
        """
        if not ObjectId.is_valid(vote_data.item_id):
            raise ValueError("Invalid item_id")

        item_oid = ObjectId(vote_data.item_id)

        # Check if item exists
        item = await self.queue_collection.find_one({"_id": item_oid})
        if not item:
            raise ValueError("Item not found")

        # Upsert the vote — the unique index on (item_id, user_id) prevents duplicates
        vote_doc = await self.votes_collection.find_one_and_update(
            {
                "item_id": item_oid,
                "user_id": vote_data.user_id,
            },
            {
                "$set": {
                    "vote": vote_data.vote.value,
                    "voted_at": datetime.utcnow(),
                },
                "$setOnInsert": {
                    "item_id": item_oid,
                    "user_id": vote_data.user_id,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        # Update denormalized vote counts on the queue item
        await self._recalculate_vote_counts(item_oid)

        return Vote(
            item_id=vote_data.item_id,
            user_id=vote_data.user_id,
            vote=VoteType(vote_doc["vote"]),
            voted_at=vote_doc["voted_at"],
        )

    async def remove_vote(self, item_id: str, user_id: str) -> bool:
        """Remove a user's vote from an item."""
        if not ObjectId.is_valid(item_id):
            return False

        item_oid = ObjectId(item_id)

        result = await self.votes_collection.delete_one({
            "item_id": item_oid,
            "user_id": user_id,
        })

        if result.deleted_count > 0:
            await self._recalculate_vote_counts(item_oid)
            return True
        return False

    async def get_vote(self, item_id: str, user_id: str) -> Vote | None:
        """Get a user's vote on an item."""
        if not ObjectId.is_valid(item_id):
            return None

        vote_doc = await self.votes_collection.find_one({
            "item_id": ObjectId(item_id),
            "user_id": user_id,
        })

        if vote_doc:
            return Vote(
                item_id=item_id,
                user_id=user_id,
                vote=VoteType(vote_doc["vote"]),
                voted_at=vote_doc["voted_at"],
            )
        return None

    async def get_item_votes(self, item_id: str) -> list[Vote]:
        """Get all votes for an item."""
        if not ObjectId.is_valid(item_id):
            return []

        item_oid = ObjectId(item_id)
        votes = []

        async for vote_doc in self.votes_collection.find({"item_id": item_oid}):
            votes.append(Vote(
                item_id=item_id,
                user_id=vote_doc["user_id"],
                vote=VoteType(vote_doc["vote"]),
                voted_at=vote_doc["voted_at"],
            ))

        return votes

    async def get_user_votes_in_room(
        self,
        room_id: str,
        user_id: str,
    ) -> dict[str, VoteType]:
        """Get all of a user's votes in a room.

        Returns a dict mapping item_id to vote type.
        """
        if not ObjectId.is_valid(room_id):
            return {}

        room_oid = ObjectId(room_id)

        # Get all item IDs in the room
        item_ids = await self.queue_collection.distinct("_id", {"room_id": room_oid})

        # Get user's votes for those items
        votes = {}
        async for vote_doc in self.votes_collection.find({
            "item_id": {"$in": item_ids},
            "user_id": user_id,
        }):
            votes[str(vote_doc["item_id"])] = VoteType(vote_doc["vote"])

        return votes

    async def _recalculate_vote_counts(self, item_id: ObjectId) -> tuple[int, int]:
        """Recalculate and update vote counts for an item.

        Returns (upvotes, downvotes).
        """
        pipeline = [
            {"$match": {"item_id": item_id}},
            {
                "$group": {
                    "_id": "$vote",
                    "count": {"$sum": 1},
                }
            },
        ]

        counts = {"up": 0, "down": 0}
        async for doc in self.votes_collection.aggregate(pipeline):
            counts[doc["_id"]] = doc["count"]

        upvotes = counts["up"]
        downvotes = counts["down"]
        vote_score = upvotes - downvotes

        await self.queue_collection.update_one(
            {"_id": item_id},
            {
                "$set": {
                    "upvotes": upvotes,
                    "downvotes": downvotes,
                    "vote_score": vote_score,
                }
            },
        )

        return upvotes, downvotes

    async def get_vote_counts(self, item_id: str) -> dict[str, int]:
        """Get vote counts for an item."""
        if not ObjectId.is_valid(item_id):
            return {"upvotes": 0, "downvotes": 0, "vote_score": 0}

        item = await self.queue_collection.find_one(
            {"_id": ObjectId(item_id)},
            {"upvotes": 1, "downvotes": 1, "vote_score": 1},
        )

        if item:
            return {
                "upvotes": item.get("upvotes", 0),
                "downvotes": item.get("downvotes", 0),
                "vote_score": item.get("vote_score", 0),
            }
        return {"upvotes": 0, "downvotes": 0, "vote_score": 0}

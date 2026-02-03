"""History service for tracking watched movies/shows."""

from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.models.watch_history import WatchHistory, WatchHistoryCreate
from app.models.queue_item import QueueItemStatus


class HistoryService:
    """Service for managing watch history."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.watch_history
        self.queue_collection = db.queue_items

    async def mark_as_watched(
        self,
        history_data: WatchHistoryCreate,
    ) -> WatchHistory:
        """Mark an item as watched and create a history entry.

        Also updates the queue item status to WATCHED.
        """
        if not ObjectId.is_valid(history_data.room_id):
            raise ValueError("Invalid room_id")
        if not ObjectId.is_valid(history_data.item_id):
            raise ValueError("Invalid item_id")

        room_oid = ObjectId(history_data.room_id)
        item_oid = ObjectId(history_data.item_id)

        # Verify item exists and belongs to room
        item = await self.queue_collection.find_one({
            "_id": item_oid,
            "room_id": room_oid,
        })
        if not item:
            raise ValueError("Item not found in room")

        # Create history entry
        history_doc = {
            "room_id": room_oid,
            "item_id": item_oid,
            "watched_at": datetime.utcnow(),
            "ratings": {},
            "notes": history_data.notes,
        }

        try:
            result = await self.collection.insert_one(history_doc)
            history_doc["_id"] = str(result.inserted_id)
        except DuplicateKeyError:
            # Item already in history
            existing = await self.collection.find_one({"item_id": item_oid})
            if existing:
                existing["_id"] = str(existing["_id"])
                existing["room_id"] = str(existing["room_id"])
                existing["item_id"] = str(existing["item_id"])
                return WatchHistory(**existing)
            raise

        # Update queue item status
        await self.queue_collection.update_one(
            {"_id": item_oid},
            {"$set": {"status": QueueItemStatus.WATCHED.value}},
        )

        history_doc["room_id"] = str(history_doc["room_id"])
        history_doc["item_id"] = str(history_doc["item_id"])
        return WatchHistory(**history_doc)

    async def get_history(self, history_id: str) -> WatchHistory | None:
        """Get a history entry by ID."""
        if not ObjectId.is_valid(history_id):
            return None

        doc = await self.collection.find_one({"_id": ObjectId(history_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
            doc["room_id"] = str(doc["room_id"])
            doc["item_id"] = str(doc["item_id"])
            return WatchHistory(**doc)
        return None

    async def get_room_history(
        self,
        room_id: str,
        limit: int = 50,
        skip: int = 0,
    ) -> list[WatchHistory]:
        """Get watch history for a room, most recent first."""
        if not ObjectId.is_valid(room_id):
            return []

        history = []
        cursor = self.collection.find(
            {"room_id": ObjectId(room_id)}
        ).sort("watched_at", -1).skip(skip).limit(limit)

        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            doc["room_id"] = str(doc["room_id"])
            doc["item_id"] = str(doc["item_id"])
            history.append(WatchHistory(**doc))

        return history

    async def add_rating(
        self,
        history_id: str,
        user_id: str,
        rating: int,
    ) -> WatchHistory | None:
        """Add or update a user's rating for a watched item.

        Rating must be 1-5.
        """
        if not ObjectId.is_valid(history_id):
            return None

        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(history_id)},
            {"$set": {f"ratings.{user_id}": rating}},
            return_document=True,
        )

        if result:
            result["_id"] = str(result["_id"])
            result["room_id"] = str(result["room_id"])
            result["item_id"] = str(result["item_id"])
            return WatchHistory(**result)
        return None

    async def update_notes(
        self,
        history_id: str,
        notes: str,
    ) -> WatchHistory | None:
        """Update notes for a history entry."""
        if not ObjectId.is_valid(history_id):
            return None

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(history_id)},
            {"$set": {"notes": notes}},
            return_document=True,
        )

        if result:
            result["_id"] = str(result["_id"])
            result["room_id"] = str(result["room_id"])
            result["item_id"] = str(result["item_id"])
            return WatchHistory(**result)
        return None

    async def get_stats(self, room_id: str) -> dict:
        """Get watch statistics for a room."""
        if not ObjectId.is_valid(room_id):
            return {}

        room_oid = ObjectId(room_id)

        # Count total watched
        total_watched = await self.collection.count_documents({"room_id": room_oid})

        # Get average ratings
        pipeline = [
            {"$match": {"room_id": room_oid}},
            {"$project": {"ratings_array": {"$objectToArray": "$ratings"}}},
            {"$unwind": "$ratings_array"},
            {
                "$group": {
                    "_id": None,
                    "avg_rating": {"$avg": "$ratings_array.v"},
                    "total_ratings": {"$sum": 1},
                }
            },
        ]

        rating_stats = {"avg_rating": None, "total_ratings": 0}
        async for doc in self.collection.aggregate(pipeline):
            rating_stats = {
                "avg_rating": round(doc["avg_rating"], 2),
                "total_ratings": doc["total_ratings"],
            }

        return {
            "total_watched": total_watched,
            **rating_stats,
        }

    async def get_history_for_item(self, item_id: str) -> WatchHistory | None:
        """Get history entry for a specific item."""
        if not ObjectId.is_valid(item_id):
            return None

        doc = await self.collection.find_one({"item_id": ObjectId(item_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
            doc["room_id"] = str(doc["room_id"])
            doc["item_id"] = str(doc["item_id"])
            return WatchHistory(**doc)
        return None

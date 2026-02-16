"""Service for queue item emoji reactions."""

from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.models.reaction import ALLOWED_REACTIONS


class ReactionService:
    """Manages add/remove reaction toggles and room-level reaction reads."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.reactions_collection = db.reactions
        self.queue_collection = db.queue_items

    async def toggle_reaction(self, item_id: str, user_id: str, reaction: str) -> bool:
        """Toggle reaction on an item.

        Returns True if reaction is now active (inserted), False if removed.
        """
        if reaction not in ALLOWED_REACTIONS:
            raise ValueError(f"Invalid reaction. Allowed: {', '.join(ALLOWED_REACTIONS)}")
        if not ObjectId.is_valid(item_id):
            raise ValueError("Invalid item_id")

        item_oid = ObjectId(item_id)
        item = await self.queue_collection.find_one({"_id": item_oid})
        if not item:
            raise ValueError("Item not found")

        query = {"item_id": item_oid, "user_id": user_id, "reaction": reaction}
        existing = await self.reactions_collection.find_one(query, {"_id": 1})
        if existing:
            await self.reactions_collection.delete_one({"_id": existing["_id"]})
            return False

        try:
            await self.reactions_collection.insert_one(
                {
                    "item_id": item_oid,
                    "user_id": user_id,
                    "reaction": reaction,
                    "reacted_at": datetime.utcnow(),
                }
            )
        except DuplicateKeyError:
            # Another request inserted concurrently; reaction is active.
            return True
        return True

    async def get_room_reactions(self, room_id: str) -> dict[str, dict[str, list[str]]]:
        """Return map of item_id to reaction->user_ids for queued room items."""
        if not ObjectId.is_valid(room_id):
            return {}

        room_oid = ObjectId(room_id)
        pipeline = [
            {
                "$lookup": {
                    "from": "queue_items",
                    "localField": "item_id",
                    "foreignField": "_id",
                    "as": "item",
                }
            },
            {"$unwind": "$item"},
            {"$match": {"item.room_id": room_oid}},
            {"$project": {"_id": 0, "item_id": 1, "reaction": 1, "user_id": 1}},
        ]

        reactions_by_item: dict[str, dict[str, list[str]]] = {}
        async for doc in self.reactions_collection.aggregate(pipeline):
            item_id = str(doc["item_id"])
            reaction = doc["reaction"]
            user_id = doc["user_id"]

            item_map = reactions_by_item.setdefault(item_id, {})
            users = item_map.setdefault(reaction, [])
            users.append(user_id)

        return reactions_by_item

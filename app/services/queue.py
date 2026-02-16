"""Queue service for managing movie/show queue."""

import re
import asyncio
from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.models.queue_item import (
    QueueItem,
    QueueItemCreate,
    QueueItemUpdate,
    QueueItemStatus,
)


class QueueService:
    """Service for managing the watch queue."""

    _add_locks: dict[str, asyncio.Lock] = {}

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.queue_items

    @classmethod
    def _get_add_lock(cls, room_id: str, title: str) -> asyncio.Lock:
        key = f"{room_id}:{title.strip().lower()}"
        if key not in cls._add_locks:
            cls._add_locks[key] = asyncio.Lock()
        return cls._add_locks[key]

    async def add_item(self, item_data: QueueItemCreate) -> QueueItem:
        """Add an item to the queue.

        Handles duplicate prevention - if the same movie (by title or tmdb_id)
        already exists in the room's queue, returns the existing item.
        """
        if not ObjectId.is_valid(item_data.room_id):
            raise ValueError("Invalid room_id")

        room_oid = ObjectId(item_data.room_id)
        lock = self._get_add_lock(item_data.room_id, item_data.title)
        async with lock:

            existing = await self.collection.find_one({
                "room_id": room_oid,
                "title": {"$regex": f"^{re.escape(item_data.title)}$", "$options": "i"},
                "status": {"$ne": QueueItemStatus.REMOVED.value},
            })
            if existing:
                existing["_id"] = str(existing["_id"])
                existing["room_id"] = str(existing["room_id"])
                return QueueItem(**existing)

            # Check for existing item by TMDB ID if provided
            if item_data.tmdb_id:
                existing = await self.collection.find_one({
                    "room_id": room_oid,
                    "tmdb_id": item_data.tmdb_id,
                    "status": {"$ne": QueueItemStatus.REMOVED.value},
                })
                if existing:
                    existing["_id"] = str(existing["_id"])
                    existing["room_id"] = str(existing["room_id"])
                    return QueueItem(**existing)

            item_doc = {
                "room_id": room_oid,
                "title": item_data.title,
                "tmdb_id": item_data.tmdb_id,
                "poster_url": item_data.poster_url,
                "year": item_data.year,
                "runtime_minutes": item_data.runtime_minutes,
                "genres": item_data.genres or [],
                "streaming_on": [],
                "play_now_url": None,
                "provider_links": [],
                "providers_by_region": {},
                "added_by": item_data.added_by,
                "added_at": datetime.utcnow(),
                "status": QueueItemStatus.QUEUED.value,
                "vote_score": 0,
                "upvotes": 0,
                "downvotes": 0,
                "overview": item_data.overview,
                "vote_average": item_data.vote_average,
            }

            try:
                result = await self.collection.insert_one(item_doc)
                item_doc["_id"] = str(result.inserted_id)
                item_doc["room_id"] = str(item_doc["room_id"])
                return QueueItem(**item_doc)
            except DuplicateKeyError:
                # Race condition: another request added the same item
                # Fetch and return the existing item
                existing = await self.collection.find_one({
                    "room_id": room_oid,
                    "title": {"$regex": f"^{item_data.title}$", "$options": "i"},
                })
                if existing:
                    existing["_id"] = str(existing["_id"])
                    existing["room_id"] = str(existing["room_id"])
                    return QueueItem(**existing)
                raise

    async def get_item(self, item_id: str) -> QueueItem | None:
        """Get a queue item by ID."""
        if not ObjectId.is_valid(item_id):
            return None

        item = await self.collection.find_one({"_id": ObjectId(item_id)})
        if item:
            item["_id"] = str(item["_id"])
            item["room_id"] = str(item["room_id"])
            return QueueItem(**item)
        return None

    async def get_room_queue(
        self,
        room_id: str,
        status: QueueItemStatus | None = None,
        provider: str | None = None,
        available_now: bool = False,
        limit: int = 100,
        skip: int = 0,
    ) -> list[QueueItem]:
        """Get all queue items for a room, sorted by vote score."""
        if not ObjectId.is_valid(room_id):
            return []

        query = {"room_id": ObjectId(room_id)}
        if status:
            query["status"] = status.value
        else:
            # Default to showing queued items
            query["status"] = {"$nin": [QueueItemStatus.REMOVED.value]}
        if provider:
            query["streaming_on"] = {"$regex": f"^{re.escape(provider)}$", "$options": "i"}
        if available_now:
            query["streaming_on.0"] = {"$exists": True}

        cursor = self.collection.find(query).sort([
            ("vote_score", -1),
            ("added_at", 1),
        ]).skip(skip).limit(limit)

        items = []
        async for item in cursor:
            item["_id"] = str(item["_id"])
            item["room_id"] = str(item["room_id"])
            items.append(QueueItem(**item))
        return items

    async def update_item(
        self,
        item_id: str,
        update_data: QueueItemUpdate,
    ) -> QueueItem | None:
        """Update a queue item."""
        if not ObjectId.is_valid(item_id):
            return None

        update_dict = update_data.model_dump(exclude_unset=True)
        if not update_dict:
            return await self.get_item(item_id)

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(item_id)},
            {"$set": update_dict},
            return_document=True,
        )
        if result:
            result["_id"] = str(result["_id"])
            result["room_id"] = str(result["room_id"])
            return QueueItem(**result)
        return None

    async def enrich_item(
        self,
        item_id: str,
        poster_url: str | None = None,
        year: int | None = None,
        runtime_minutes: int | None = None,
        genres: list[str] | None = None,
        streaming_on: list[str] | None = None,
        play_now_url: str | None = None,
        provider_links: list[dict] | None = None,
        providers_by_region: dict[str, list[str]] | None = None,
        tmdb_id: int | None = None,
    ) -> QueueItem | None:
        """Enrich a queue item with metadata from external APIs."""
        if not ObjectId.is_valid(item_id):
            return None

        update = {}
        if poster_url is not None:
            update["poster_url"] = poster_url
        if year is not None:
            update["year"] = year
        if runtime_minutes is not None:
            update["runtime_minutes"] = runtime_minutes
        if genres is not None:
            update["genres"] = genres
        if streaming_on is not None:
            update["streaming_on"] = streaming_on
        if play_now_url is not None:
            update["play_now_url"] = play_now_url
        if provider_links is not None:
            update["provider_links"] = provider_links
        if providers_by_region is not None:
            update["providers_by_region"] = providers_by_region
        if tmdb_id is not None:
            update["tmdb_id"] = tmdb_id

        if not update:
            return await self.get_item(item_id)

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(item_id)},
            {"$set": update},
            return_document=True,
        )
        if result:
            result["_id"] = str(result["_id"])
            result["room_id"] = str(result["room_id"])
            return QueueItem(**result)
        return None

    async def remove_item(self, item_id: str) -> bool:
        """Remove an item from the queue (soft delete)."""
        if not ObjectId.is_valid(item_id):
            return False

        result = await self.collection.update_one(
            {"_id": ObjectId(item_id)},
            {"$set": {"status": QueueItemStatus.REMOVED.value}},
        )
        return result.modified_count > 0

    async def mark_watching(self, item_id: str) -> QueueItem | None:
        """Mark an item as currently being watched."""
        return await self.update_item(
            item_id,
            QueueItemUpdate(status=QueueItemStatus.WATCHING),
        )

    async def mark_watched(self, item_id: str) -> QueueItem | None:
        """Mark an item as watched."""
        return await self.update_item(
            item_id,
            QueueItemUpdate(status=QueueItemStatus.WATCHED),
        )

    async def update_vote_counts(
        self,
        item_id: str,
        upvotes: int,
        downvotes: int,
    ) -> QueueItem | None:
        """Update the denormalized vote counts for an item."""
        if not ObjectId.is_valid(item_id):
            return None

        vote_score = upvotes - downvotes

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(item_id)},
            {
                "$set": {
                    "upvotes": upvotes,
                    "downvotes": downvotes,
                    "vote_score": vote_score,
                }
            },
            return_document=True,
        )
        if result:
            result["_id"] = str(result["_id"])
            result["room_id"] = str(result["room_id"])
            return QueueItem(**result)
        return None

    async def get_top_items(
        self,
        room_id: str,
        limit: int = 10,
    ) -> list[QueueItem]:
        """Get top voted items in a room's queue."""
        return await self.get_room_queue(
            room_id,
            status=QueueItemStatus.QUEUED,
            limit=limit,
        )

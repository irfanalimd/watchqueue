"""Room service for managing watch rooms."""

import secrets
import string
from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.room import (
    Room,
    RoomCreate,
    RoomUpdate,
    RoomSettings,
    Member,
)
from app.config import get_settings


class RoomService:
    """Service for managing rooms."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.rooms

    def _generate_room_code(self) -> str:
        """Generate a unique room code."""
        settings = get_settings()
        chars = string.ascii_uppercase + string.digits
        # Remove confusing characters
        chars = chars.replace("0", "").replace("O", "").replace("I", "").replace("1", "")
        return "".join(secrets.choice(chars) for _ in range(settings.room_code_length))

    @staticmethod
    def _normalize_member_name(name: str) -> str:
        """Normalize member name for uniqueness checks."""
        return name.strip().lower()

    @staticmethod
    def _normalize_region(region: str) -> str:
        """Normalize region value."""
        return region.strip().upper()

    async def create_room(self, room_data: RoomCreate) -> Room:
        """Create a new room with a unique join code."""
        existing_name = await self.collection.find_one({
            "name": {"$regex": f"^{room_data.name}$", "$options": "i"}
        })
        if existing_name:
            raise ValueError("Room name already exists, choose another name")

        # Enforce unique member names (case-insensitive) inside a room
        seen_names: set[str] = set()
        for member in room_data.members:
            member.region = self._normalize_region(member.region)
            normalized = self._normalize_member_name(member.name)
            if normalized in seen_names:
                raise ValueError("User already exists, choose another name")
            seen_names.add(normalized)

        # Generate unique code with retry
        max_attempts = 10
        for _ in range(max_attempts):
            code = self._generate_room_code()
            existing = await self.collection.find_one({"code": code})
            if not existing:
                break
        else:
            raise RuntimeError("Failed to generate unique room code")

        room_doc = {
            "name": room_data.name,
            "code": code,
            "members": [m.model_dump() for m in room_data.members],
            "admins": [room_data.members[0].user_id] if room_data.members else [],
            "settings": room_data.settings.model_dump(),
            "created_at": datetime.utcnow(),
        }

        result = await self.collection.insert_one(room_doc)
        room_doc["_id"] = str(result.inserted_id)
        return Room(**room_doc)

    async def get_room(self, room_id: str) -> Room | None:
        """Get a room by ID."""
        if not ObjectId.is_valid(room_id):
            return None
        room_doc = await self.collection.find_one({"_id": ObjectId(room_id)})
        if room_doc:
            room_doc["_id"] = str(room_doc["_id"])
            room_doc.setdefault("admins", [])
            return Room(**room_doc)
        return None

    async def get_room_by_code(self, code: str) -> Room | None:
        """Get a room by its join code."""
        room_doc = await self.collection.find_one({"code": code.upper()})
        if room_doc:
            room_doc["_id"] = str(room_doc["_id"])
            room_doc.setdefault("admins", [])
            return Room(**room_doc)
        return None

    async def update_room(self, room_id: str, room_update: RoomUpdate) -> Room | None:
        """Update a room's settings or name."""
        if not ObjectId.is_valid(room_id):
            return None

        update_data = {}
        if room_update.name is not None:
            update_data["name"] = room_update.name
        if room_update.settings is not None:
            update_data["settings"] = room_update.settings.model_dump()

        if not update_data:
            return await self.get_room(room_id)

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(room_id)},
            {"$set": update_data},
            return_document=True,
        )
        if result:
            result["_id"] = str(result["_id"])
            result.setdefault("admins", [])
            return Room(**result)
        return None

    async def delete_room(self, room_id: str) -> bool:
        """Delete a room and all associated data."""
        if not ObjectId.is_valid(room_id):
            return False

        oid = ObjectId(room_id)

        # Delete room
        result = await self.collection.delete_one({"_id": oid})
        if result.deleted_count == 0:
            return False

        # Get item IDs before deleting queue items (needed for vote cleanup)
        item_ids = await self.db.queue_items.distinct("_id", {"room_id": oid})

        # Clean up related data
        await self.db.queue_items.delete_many({"room_id": oid})
        await self.db.watch_history.delete_many({"room_id": oid})

        # Delete votes for items in this room
        if item_ids:
            await self.db.votes.delete_many({"item_id": {"$in": item_ids}})

        return True

    async def list_rooms_for_member(self, user_id: str) -> list[Room]:
        """List all rooms where a user is a member."""
        cursor = self.collection.find({"members.user_id": user_id}).sort("created_at", -1)
        rooms: list[Room] = []
        async for room_doc in cursor:
            room_doc["_id"] = str(room_doc["_id"])
            room_doc.setdefault("admins", [])
            rooms.append(Room(**room_doc))
        return rooms

    async def add_member(self, room_id: str, member: Member) -> Room | None:
        """Add a member to a room."""
        if not ObjectId.is_valid(room_id):
            return None

        room_doc = await self.collection.find_one({"_id": ObjectId(room_id)})
        if not room_doc:
            return None

        member.region = self._normalize_region(member.region)
        # Check if member already exists
        existing = next(
            (m for m in room_doc.get("members", []) if m.get("user_id") == member.user_id),
            None,
        )
        if existing is not None:
            # Member already in room: joining again should be idempotent and non-mutating.
            room_doc["_id"] = str(room_doc["_id"])
            room_doc.setdefault("admins", [])
            return Room(**room_doc)

        normalized_name = self._normalize_member_name(member.name)
        name_taken = any(
            self._normalize_member_name(m.get("name", "")) == normalized_name
            for m in room_doc.get("members", [])
        )
        if name_taken:
            raise ValueError("User already exists, choose another name")

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(room_id)},
            {"$push": {"members": member.model_dump()}},
            return_document=True,
        )
        if result:
            result["_id"] = str(result["_id"])
            result.setdefault("admins", [])
            return Room(**result)
        return None

    async def remove_member(self, room_id: str, user_id: str) -> Room | None:
        """Remove a member from a room."""
        if not ObjectId.is_valid(room_id):
            return None

        result = await self.collection.find_one_and_update(
            {"_id": ObjectId(room_id)},
            {"$pull": {"members": {"user_id": user_id}}},
            return_document=True,
        )
        if result:
            result["_id"] = str(result["_id"])
            result.setdefault("admins", [])
            return Room(**result)
        return None

    async def update_member(self, room_id: str, member: Member) -> Room | None:
        """Update a member's info (name, avatar)."""
        if not ObjectId.is_valid(room_id):
            return None

        room_doc = await self.collection.find_one({"_id": ObjectId(room_id)})
        if not room_doc:
            return None

        member.region = self._normalize_region(member.region)
        normalized_name = self._normalize_member_name(member.name)
        name_taken = any(
            m.get("user_id") != member.user_id
            and self._normalize_member_name(m.get("name", "")) == normalized_name
            for m in room_doc.get("members", [])
        )
        if name_taken:
            raise ValueError("User already exists, choose another name")

        result = await self.collection.find_one_and_update(
            {
                "_id": ObjectId(room_id),
                "members.user_id": member.user_id,
            },
            {
                "$set": {
                    "members.$.name": member.name,
                    "members.$.avatar": member.avatar,
                    "members.$.region": member.region,
                }
            },
            return_document=True,
        )
        if result:
            result["_id"] = str(result["_id"])
            return Room(**result)
        return None

    async def is_member(self, room_id: str, user_id: str) -> bool:
        """Check if a user is a member of a room."""
        if not ObjectId.is_valid(room_id):
            return False

        result = await self.collection.find_one({
            "_id": ObjectId(room_id),
            "members.user_id": user_id,
        })
        return result is not None

    async def is_admin(self, room_id: str, user_id: str) -> bool:
        """Check if a user is an admin of a room."""
        if not ObjectId.is_valid(room_id):
            return False

        result = await self.collection.find_one({
            "_id": ObjectId(room_id),
            "admins": user_id,
        })
        return result is not None

    async def grant_admin(self, room_id: str, target_user_id: str) -> Room | None:
        """Grant admin privileges to a room member."""
        if not ObjectId.is_valid(room_id):
            return None

        result = await self.collection.find_one_and_update(
            {
                "_id": ObjectId(room_id),
                "members.user_id": target_user_id,
            },
            {"$addToSet": {"admins": target_user_id}},
            return_document=True,
        )
        if result:
            result["_id"] = str(result["_id"])
            result.setdefault("admins", [])
            return Room(**result)
        return None

    async def leave_room(
        self,
        room_id: str,
        user_id: str,
        new_admin_user_id: str | None = None,
    ) -> Room | None:
        """Leave a room with admin handoff constraints."""
        if not ObjectId.is_valid(room_id):
            return None

        room_doc = await self.collection.find_one({"_id": ObjectId(room_id)})
        if not room_doc:
            return None

        members = room_doc.get("members", [])
        admins = room_doc.get("admins", [])
        member_ids = [m.get("user_id") for m in members]
        if user_id not in member_ids:
            # Idempotent leave for stale clients: room exists, user already not a member.
            room_doc["_id"] = str(room_doc["_id"])
            room_doc.setdefault("admins", [])
            return Room(**room_doc)

        is_admin = user_id in admins
        if is_admin:
            other_admins = [aid for aid in admins if aid != user_id and aid in member_ids]

            if new_admin_user_id:
                if new_admin_user_id == user_id:
                    raise ValueError("Cannot transfer admin to yourself")
                if new_admin_user_id not in member_ids:
                    raise ValueError("New admin must be an existing room member")
                if new_admin_user_id in other_admins:
                    # already admin, no-op
                    pass
                else:
                    other_admins.append(new_admin_user_id)

            if not other_admins:
                raise ValueError(
                    "Last admin cannot leave without transferring admin privileges"
                )

            result = await self.collection.find_one_and_update(
                {"_id": ObjectId(room_id)},
                {
                    "$pull": {
                        "members": {"user_id": user_id},
                        "admins": user_id,
                    }
                },
                return_document=True,
            )
            if result and new_admin_user_id:
                result = await self.collection.find_one_and_update(
                    {"_id": ObjectId(room_id)},
                    {"$addToSet": {"admins": new_admin_user_id}},
                    return_document=True,
                )
        else:
            result = await self.collection.find_one_and_update(
                {"_id": ObjectId(room_id)},
                {"$pull": {"members": {"user_id": user_id}}},
                return_document=True,
            )

        if result:
            result["_id"] = str(result["_id"])
            result.setdefault("admins", [])
            return Room(**result)
        return None

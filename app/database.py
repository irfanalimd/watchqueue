"""MongoDB database connection and setup."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING, DESCENDING
from typing import AsyncGenerator
import logging
import certifi

from app.config import get_settings

logger = logging.getLogger(__name__)


class Database:
    """MongoDB database manager."""

    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None

    @classmethod
    async def connect(cls) -> None:
        """Connect to MongoDB and set up indexes."""
        settings = get_settings()

        client_options: dict = {
            "serverSelectionTimeoutMS": 30000,
            "connectTimeoutMS": 20000,
            "socketTimeoutMS": 20000,
        }

        # Force CA bundle usage on hosted environments (Render) to avoid TLS trust/handshake issues.
        if settings.mongodb_url.startswith("mongodb+srv://"):
            client_options["tls"] = True
            client_options["tlsCAFile"] = certifi.where()

        cls.client = AsyncIOMotorClient(settings.mongodb_url, **client_options)
        cls.db = cls.client[settings.mongodb_database]

        # Verify connectivity before proceeding to index creation/migrations.
        await cls.client.admin.command("ping")
        logger.info(f"Connected to MongoDB database: {settings.mongodb_database}")
        await cls._create_indexes()
        await cls.run_migrations()

    @classmethod
    async def disconnect(cls) -> None:
        """Disconnect from MongoDB."""
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("Disconnected from MongoDB")

    @classmethod
    async def _create_indexes(cls) -> None:
        """Create necessary indexes for all collections."""
        if cls.db is None:
            raise RuntimeError("Database not connected")

        # Rooms collection indexes
        await cls.db.rooms.create_indexes([
            IndexModel([("code", ASCENDING)], unique=True),
            IndexModel([("created_at", DESCENDING)]),
            IndexModel([("members.user_id", ASCENDING)]),
            IndexModel([("admins", ASCENDING)]),
        ])

        # Queue items collection indexes
        await cls.db.queue_items.create_indexes([
            IndexModel([
                ("room_id", ASCENDING),
                ("status", ASCENDING),
                ("vote_score", DESCENDING)
            ]),
            IndexModel([("room_id", ASCENDING), ("title", ASCENDING)]),
        ])

        # Votes collection - unique compound index prevents duplicate votes
        await cls.db.votes.create_indexes([
            IndexModel(
                [("item_id", ASCENDING), ("user_id", ASCENDING)],
                unique=True,
                name="item_user_unique",
            ),
            IndexModel([("item_id", ASCENDING)], name="item_lookup"),
        ])

        # Reactions collection - unique per item/user/reaction
        await cls.db.reactions.create_indexes([
            IndexModel(
                [("item_id", ASCENDING), ("user_id", ASCENDING), ("reaction", ASCENDING)],
                unique=True,
                name="item_user_reaction_unique",
            ),
            IndexModel([("item_id", ASCENDING)], name="reaction_item_lookup"),
        ])

        # Watch history collection indexes
        await cls.db.watch_history.create_indexes([
            IndexModel([("room_id", ASCENDING), ("watched_at", DESCENDING)]),
            IndexModel([("item_id", ASCENDING)], unique=True),
        ])

        # Users collection indexes
        await cls.db.users.create_indexes([
            IndexModel([("google_sub", ASCENDING)], unique=True),
            IndexModel([("email", ASCENDING)]),
        ])

        # Sessions collection indexes
        await cls.db.sessions.create_indexes([
            IndexModel([("token", ASCENDING)], unique=True),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0),
            IndexModel([("user_id", ASCENDING)]),
        ])

        logger.info("Database indexes created successfully")

    @classmethod
    async def run_migrations(cls) -> None:
        """Run lightweight data backfills for backward compatibility."""
        if cls.db is None:
            raise RuntimeError("Database not connected")

        # Ensure members have a region for provider availability calculations
        async for room in cls.db.rooms.find({}, {"members": 1}):
            members = room.get("members", [])
            changed = False
            normalized_members = []
            for member in members:
                normalized = dict(member)
                region = (normalized.get("region") or "US").strip().upper()
                if normalized.get("region") != region:
                    changed = True
                normalized["region"] = region
                normalized_members.append(normalized)

            if changed:
                await cls.db.rooms.update_one(
                    {"_id": room["_id"]},
                    {"$set": {"members": normalized_members}},
                )

        # Backfill missing/empty admins: make the first room member the admin.
        async for room in cls.db.rooms.find(
            {
                "$or": [
                    {"admins": {"$exists": False}},
                    {"admins": []},
                ]
            },
            {"members": 1, "admins": 1},
        ):
            members = room.get("members", [])
            first_member_id = members[0].get("user_id") if members else None
            if first_member_id:
                await cls.db.rooms.update_one(
                    {"_id": room["_id"]},
                    {"$set": {"admins": [first_member_id]}},
                )
            else:
                await cls.db.rooms.update_one(
                    {"_id": room["_id"]},
                    {"$set": {"admins": []}},
                )

        logger.info("Database migrations completed")

    @classmethod
    def get_db(cls) -> AsyncIOMotorDatabase:
        """Get the database instance."""
        if cls.db is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return cls.db


async def get_database() -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """Dependency for getting database instance."""
    yield Database.get_db()

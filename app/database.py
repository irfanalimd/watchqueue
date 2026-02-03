"""MongoDB database connection and setup."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import IndexModel, ASCENDING, DESCENDING
from typing import AsyncGenerator
import logging

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
        cls.client = AsyncIOMotorClient(settings.mongodb_url)
        cls.db = cls.client[settings.mongodb_database]
        logger.info(f"Connected to MongoDB database: {settings.mongodb_database}")
        await cls._create_indexes()

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

        # Watch history collection indexes
        await cls.db.watch_history.create_indexes([
            IndexModel([("room_id", ASCENDING), ("watched_at", DESCENDING)]),
            IndexModel([("item_id", ASCENDING)], unique=True),
        ])

        logger.info("Database indexes created successfully")

    @classmethod
    def get_db(cls) -> AsyncIOMotorDatabase:
        """Get the database instance."""
        if cls.db is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return cls.db


async def get_database() -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """Dependency for getting database instance."""
    yield Database.get_db()

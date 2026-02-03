"""Pytest configuration and fixtures for WatchQueue tests."""

import asyncio
import os
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from bson import ObjectId

# Set test environment before importing app modules
os.environ["MONGODB_URL"] = os.environ.get(
    "TEST_MONGODB_URL",
    "mongodb://localhost:27017,localhost:27018,localhost:27019/?replicaSet=rs0"
)
os.environ["MONGODB_DATABASE"] = "watchqueue_test"

from app.main import app
from app.database import Database
from app.models.room import RoomCreate, RoomSettings, Member, SelectionMode
from app.models.queue_item import QueueItemCreate
from app.services.rooms import RoomService
from app.services.queue import QueueService
from app.services.voting import VotingService
from app.services.selection import SelectionService
from app.services.history import HistoryService


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """Get test database connection and clean up after each test."""
    await Database.connect()
    database = Database.get_db()

    yield database

    # Clean up all collections after each test
    await database.rooms.delete_many({})
    await database.queue_items.delete_many({})
    await database.votes.delete_many({})
    await database.watch_history.delete_many({})

    await Database.disconnect()


@pytest_asyncio.fixture
async def client(db: AsyncIOMotorDatabase) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for API testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def room_service(db: AsyncIOMotorDatabase) -> RoomService:
    """Create room service for testing."""
    return RoomService(db)


@pytest_asyncio.fixture
async def queue_service(db: AsyncIOMotorDatabase) -> QueueService:
    """Create queue service for testing."""
    return QueueService(db)


@pytest_asyncio.fixture
async def voting_service(db: AsyncIOMotorDatabase) -> VotingService:
    """Create voting service for testing."""
    return VotingService(db)


@pytest_asyncio.fixture
async def selection_service(db: AsyncIOMotorDatabase) -> SelectionService:
    """Create selection service for testing."""
    return SelectionService(db)


@pytest_asyncio.fixture
async def history_service(db: AsyncIOMotorDatabase) -> HistoryService:
    """Create history service for testing."""
    return HistoryService(db)


@pytest_asyncio.fixture
async def movie_room(room_service: RoomService) -> dict:
    """Create a room with 4 members for testing."""
    room_data = RoomCreate(
        name="Friday Night Movies",
        members=[
            Member(user_id="alice", name="Alice", avatar="🦊"),
            Member(user_id="bob", name="Bob", avatar="🐻"),
            Member(user_id="charlie", name="Charlie", avatar="🐸"),
            Member(user_id="diana", name="Diana", avatar="🦋"),
        ],
        settings=RoomSettings(
            voting_duration_seconds=60,
            selection_mode=SelectionMode.WEIGHTED_RANDOM,
            allow_revotes=True,
        ),
    )

    room = await room_service.create_room(room_data)
    return {
        "_id": room.id,
        "name": room.name,
        "code": room.code,
        "members": [m.model_dump() for m in room.members],
        "settings": room.settings.model_dump(),
    }


@pytest_asyncio.fixture
async def queue_with_items(
    movie_room: dict,
    queue_service: QueueService,
) -> dict:
    """Create a room with several queue items."""
    room_id = movie_room["_id"]

    items = []
    test_movies = [
        ("Inception", "alice"),
        ("The Matrix", "bob"),
        ("Interstellar", "charlie"),
        ("Pulp Fiction", "diana"),
        ("The Dark Knight", "alice"),
    ]

    for title, added_by in test_movies:
        item = await queue_service.add_item(QueueItemCreate(
            room_id=room_id,
            title=title,
            added_by=added_by,
        ))
        items.append(item)

    return {
        "room": movie_room,
        "items": items,
    }


@pytest.fixture
def mock_tmdb_response():
    """Mock TMDB API response."""
    return {
        "results": [
            {
                "id": 27205,
                "title": "Inception",
                "poster_path": "/9gk7adHYeDvHkCSEqAvQNLV5Ber.jpg",
                "release_date": "2010-07-16",
                "overview": "A thief who steals corporate secrets...",
                "genre_ids": [28, 878, 53],
            }
        ]
    }


@pytest.fixture
def mock_tmdb_movie_details():
    """Mock TMDB movie details response."""
    return {
        "id": 27205,
        "title": "Inception",
        "poster_path": "/9gk7adHYeDvHkCSEqAvQNLV5Ber.jpg",
        "release_date": "2010-07-16",
        "runtime": 148,
        "genres": [
            {"id": 28, "name": "Action"},
            {"id": 878, "name": "Science Fiction"},
            {"id": 53, "name": "Thriller"},
        ],
        "overview": "A thief who steals corporate secrets...",
    }

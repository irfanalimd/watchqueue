"""Queue management API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from app.database import get_database
from app.models.queue_item import (
    QueueItem,
    QueueItemCreate,
    QueueItemUpdate,
    QueueItemStatus,
)
from app.models.room import SelectionMode
from app.services.queue import QueueService
from app.services.selection import SelectionService
from app.services.history import HistoryService
from app.services.external_api import TMDBClient, enrich_queue_item
from app.models.watch_history import WatchHistory, WatchHistoryCreate

router = APIRouter(prefix="/queue", tags=["queue"])


def get_queue_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> QueueService:
    """Dependency for queue service."""
    return QueueService(db)


def get_selection_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> SelectionService:
    """Dependency for selection service."""
    return SelectionService(db)


def get_history_service(db: AsyncIOMotorDatabase = Depends(get_database)) -> HistoryService:
    """Dependency for history service."""
    return HistoryService(db)


async def enrich_item_background(
    item_id: str,
    title: str,
    room_id: str,
    db: AsyncIOMotorDatabase,
    tmdb_id: int | None = None,
):
    """Background task to enrich item with metadata."""
    try:
        room_doc = await db.rooms.find_one({"_id": ObjectId(room_id)}, {"members": 1})
        member_regions = [
            m.get("region", "US")
            for m in (room_doc or {}).get("members", [])
            if m.get("region")
        ]
        enrichment = await enrich_queue_item(
            title,
            tmdb_id=tmdb_id,
            member_regions=member_regions,
        )
        if enrichment:
            service = QueueService(db)
            await service.enrich_item(
                item_id,
                poster_url=enrichment.get("poster_url"),
                year=enrichment.get("year"),
                runtime_minutes=enrichment.get("runtime_minutes"),
                genres=enrichment.get("genres"),
                streaming_on=enrichment.get("streaming_on"),
                play_now_url=enrichment.get("play_now_url"),
                provider_links=enrichment.get("provider_links"),
                providers_by_region=enrichment.get("providers_by_region"),
                tmdb_id=enrichment.get("tmdb_id"),
            )
    except Exception:
        pass  # Enrichment failure is non-critical


@router.get("/search/tmdb")
async def search_tmdb(
    q: str = Query(..., min_length=2, max_length=200),
    limit: int = Query(default=8, ge=1, le=20),
) -> list[dict]:
    """Search TMDB for movies and TV shows. Returns results for autocomplete."""
    client = TMDBClient()
    try:
        results = await client.search_multi(q, limit=limit)
        return [
            {
                "tmdb_id": r.tmdb_id,
                "title": r.title,
                "poster_url": r.poster_url,
                "year": r.year,
                "vote_average": r.vote_average,
                "overview": (r.overview[:150] + "...") if r.overview and len(r.overview) > 150 else r.overview,
                "genres": r.genres,
                "runtime_minutes": r.runtime_minutes,
            }
            for r in results
        ]
    finally:
        await client.close()


@router.post("", response_model=QueueItem, status_code=status.HTTP_201_CREATED)
async def add_to_queue(
    item_data: QueueItemCreate,
    background_tasks: BackgroundTasks,
    service: QueueService = Depends(get_queue_service),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> QueueItem:
    """Add an item to a room's queue.

    Automatically enriches the item with metadata in the background.
    Prevents duplicates - returns existing item if already in queue.
    """
    try:
        item = await service.add_item(item_data)
        background_tasks.add_task(
            enrich_item_background,
            item.id,
            item.title,
            item.room_id,
            db,
            item.tmdb_id,
        )
        return item
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{item_id}", response_model=QueueItem)
async def get_queue_item(
    item_id: str,
    service: QueueService = Depends(get_queue_service),
) -> QueueItem:
    """Get a queue item by ID."""
    item = await service.get_item(item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Queue item not found",
        )
    return item


@router.get("/room/{room_id}", response_model=list[QueueItem])
async def get_room_queue(
    room_id: str,
    status_filter: QueueItemStatus | None = None,
    provider: str | None = Query(default=None),
    available_now: bool = Query(default=False),
    limit: int = 100,
    skip: int = 0,
    service: QueueService = Depends(get_queue_service),
) -> list[QueueItem]:
    """Get all queue items for a room.

    Items are sorted by vote score (highest first).
    """
    return await service.get_room_queue(
        room_id,
        status=status_filter,
        provider=provider,
        available_now=available_now,
        limit=limit,
        skip=skip,
    )


@router.patch("/{item_id}", response_model=QueueItem)
async def update_queue_item(
    item_id: str,
    update_data: QueueItemUpdate,
    service: QueueService = Depends(get_queue_service),
) -> QueueItem:
    """Update a queue item."""
    item = await service.update_item(item_id, update_data)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Queue item not found",
        )
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_queue(
    item_id: str,
    service: QueueService = Depends(get_queue_service),
) -> None:
    """Remove an item from the queue (soft delete)."""
    removed = await service.remove_item(item_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Queue item not found",
        )


@router.post("/{item_id}/enrich", response_model=QueueItem)
async def enrich_item(
    item_id: str,
    service: QueueService = Depends(get_queue_service),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> QueueItem:
    """Manually trigger metadata enrichment for an item."""
    item = await service.get_item(item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Queue item not found",
        )

    room_doc = await db.rooms.find_one({"_id": ObjectId(item.room_id)}, {"members": 1})
    member_regions = [
        m.get("region", "US")
        for m in (room_doc or {}).get("members", [])
        if m.get("region")
    ]
    enrichment = await enrich_queue_item(
        item.title,
        tmdb_id=item.tmdb_id,
        member_regions=member_regions,
    )
    if enrichment:
        item = await service.enrich_item(
            item_id,
            poster_url=enrichment.get("poster_url"),
            year=enrichment.get("year"),
            runtime_minutes=enrichment.get("runtime_minutes"),
            genres=enrichment.get("genres"),
            streaming_on=enrichment.get("streaming_on"),
            play_now_url=enrichment.get("play_now_url"),
            provider_links=enrichment.get("provider_links"),
            providers_by_region=enrichment.get("providers_by_region"),
            tmdb_id=enrichment.get("tmdb_id"),
        )

    if not item:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enrich item",
        )
    return item


@router.post("/room/{room_id}/select", response_model=QueueItem)
async def select_next(
    room_id: str,
    mode: SelectionMode | None = None,
    selection_service: SelectionService = Depends(get_selection_service),
) -> QueueItem:
    """Select the next item to watch based on selection mode.

    Uses the room's configured selection mode if not specified.
    """
    item = await selection_service.select_next(room_id, mode=mode)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No items in queue or room not found",
        )
    return item


@router.post("/room/{room_id}/voting-round")
async def start_voting_round(
    room_id: str,
    duration_seconds: int | None = None,
    selection_service: SelectionService = Depends(get_selection_service),
) -> dict:
    """Start a timed voting round.

    Returns voting round info for clients to display countdown.
    """
    try:
        return await selection_service.start_voting_round(room_id, duration_seconds)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{item_id}/watch", response_model=WatchHistory)
async def mark_as_watching(
    item_id: str,
    notes: str | None = None,
    queue_service: QueueService = Depends(get_queue_service),
    history_service: HistoryService = Depends(get_history_service),
) -> WatchHistory:
    """Mark an item as currently being watched.

    Creates a history entry and updates item status.
    """
    item = await queue_service.get_item(item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Queue item not found",
        )

    # Update status to watching
    await queue_service.mark_watching(item_id)

    # Create history entry
    try:
        history = await history_service.mark_as_watched(
            WatchHistoryCreate(
                room_id=item.room_id,
                item_id=item_id,
                notes=notes,
            )
        )
        return history
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/room/{room_id}/stats")
async def get_selection_stats(
    room_id: str,
    selection_service: SelectionService = Depends(get_selection_service),
) -> dict:
    """Get selection fairness statistics for a room."""
    return await selection_service.get_selection_stats(room_id)

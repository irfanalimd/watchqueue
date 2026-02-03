"""Server-Sent Events (SSE) endpoints for MongoDB change streams."""

import asyncio
import json
import logging
from datetime import datetime
from typing import AsyncGenerator
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from bson import ObjectId

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/events", tags=["sse"])


async def serialize_change(change: dict) -> dict:
    """Serialize a MongoDB change stream event for JSON output."""
    result = {
        "operation": change.get("operationType"),
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Handle document key
    if "documentKey" in change:
        result["document_id"] = str(change["documentKey"]["_id"])

    # Handle full document for inserts and updates
    if "fullDocument" in change and change["fullDocument"]:
        doc = change["fullDocument"]
        # Convert ObjectIds to strings
        serialized = {}
        for key, value in doc.items():
            if isinstance(value, ObjectId):
                serialized[key] = str(value)
            elif isinstance(value, datetime):
                serialized[key] = value.isoformat()
            else:
                serialized[key] = value
        result["document"] = serialized

    # Handle update description
    if "updateDescription" in change:
        result["updated_fields"] = change["updateDescription"].get("updatedFields", {})
        result["removed_fields"] = change["updateDescription"].get("removedFields", [])

    return result


async def generate_vote_events(room_id: str, request: Request) -> AsyncGenerator[str, None]:
    """Generate SSE events for vote changes in a room.

    Watches the votes collection for changes on items in the specified room.
    """
    db = Database.get_db()

    # First, get all item IDs in this room
    item_ids = await db.queue_items.distinct("_id", {"room_id": ObjectId(room_id)})

    if not item_ids:
        yield f"data: {json.dumps({'type': 'info', 'message': 'No items in room'})}\n\n"
        return

    # Watch votes collection for these items (top-level item_id field)
    pipeline = [
        {"$match": {"fullDocument.item_id": {"$in": item_ids}}}
    ]

    try:
        async with db.votes.watch(
            pipeline,
            full_document="updateLookup",
        ) as stream:
            yield f"data: {json.dumps({'type': 'connected', 'room_id': room_id})}\n\n"

            async for change in stream:
                if await request.is_disconnected():
                    break

                event = await serialize_change(change)
                event["type"] = "vote_change"

                # Get updated vote counts for the item
                if "document" in event and "item_id" in event["document"]:
                    item_id = event["document"]["item_id"]
                    if item_id:
                        item = await db.queue_items.find_one(
                            {"_id": ObjectId(item_id)},
                            {"upvotes": 1, "downvotes": 1, "vote_score": 1},
                        )
                        if item:
                            event["vote_counts"] = {
                                "upvotes": item.get("upvotes", 0),
                                "downvotes": item.get("downvotes", 0),
                                "vote_score": item.get("vote_score", 0),
                            }

                yield f"data: {json.dumps(event)}\n\n"

    except Exception as e:
        logger.error(f"Vote stream error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


async def generate_queue_events(room_id: str, request: Request) -> AsyncGenerator[str, None]:
    """Generate SSE events for queue changes in a room."""
    db = Database.get_db()

    pipeline = [
        {"$match": {"fullDocument.room_id": ObjectId(room_id)}}
    ]

    try:
        async with db.queue_items.watch(
            pipeline,
            full_document="updateLookup",
        ) as stream:
            yield f"data: {json.dumps({'type': 'connected', 'room_id': room_id})}\n\n"

            async for change in stream:
                if await request.is_disconnected():
                    break

                event = await serialize_change(change)
                event["type"] = "queue_change"
                yield f"data: {json.dumps(event)}\n\n"

    except Exception as e:
        logger.error(f"Queue stream error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


async def generate_room_events(room_id: str, request: Request) -> AsyncGenerator[str, None]:
    """Generate SSE events for all changes in a room.

    Combines vote and queue events into a single stream.
    """
    db = Database.get_db()

    yield f"data: {json.dumps({'type': 'connected', 'room_id': room_id})}\n\n"

    # Create tasks for both streams
    async def watch_votes():
        item_ids = await db.queue_items.distinct("_id", {"room_id": ObjectId(room_id)})
        if not item_ids:
            return

        pipeline = [{"$match": {"fullDocument.item_id": {"$in": item_ids}}}]
        async with db.votes.watch(pipeline, full_document="updateLookup") as stream:
            async for change in stream:
                event = await serialize_change(change)
                event["type"] = "vote_change"
                yield event

    async def watch_queue():
        pipeline = [{"$match": {"fullDocument.room_id": ObjectId(room_id)}}]
        async with db.queue_items.watch(pipeline, full_document="updateLookup") as stream:
            async for change in stream:
                event = await serialize_change(change)
                event["type"] = "queue_change"
                yield event

    # Merge both streams
    vote_gen = watch_votes()
    queue_gen = watch_queue()

    pending = {
        asyncio.create_task(vote_gen.__anext__()): vote_gen,
        asyncio.create_task(queue_gen.__anext__()): queue_gen,
    }

    try:
        while pending and not await request.is_disconnected():
            done, _ = await asyncio.wait(
                pending.keys(),
                return_when=asyncio.FIRST_COMPLETED,
                timeout=30.0,
            )

            if not done:
                # Timeout - send keepalive
                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                continue

            for task in done:
                gen = pending.pop(task)
                try:
                    event = task.result()
                    yield f"data: {json.dumps(event)}\n\n"
                    # Schedule next event from this generator
                    pending[asyncio.create_task(gen.__anext__())] = gen
                except StopAsyncIteration:
                    pass
                except Exception as e:
                    logger.error(f"Stream error: {e}")

    finally:
        for task in pending:
            task.cancel()


@router.get("/votes/{room_id}")
async def stream_vote_events(room_id: str, request: Request):
    """Stream real-time vote updates for a room.

    Uses MongoDB change streams to push vote changes to clients.
    """
    return StreamingResponse(
        generate_vote_events(room_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/queue/{room_id}")
async def stream_queue_events(room_id: str, request: Request):
    """Stream real-time queue updates for a room."""
    return StreamingResponse(
        generate_queue_events(room_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/room/{room_id}")
async def stream_room_events(room_id: str, request: Request):
    """Stream all real-time updates for a room (votes + queue)."""
    return StreamingResponse(
        generate_room_events(room_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

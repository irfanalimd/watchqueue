"""Backfill queue provider metadata from TMDB watch providers."""

import argparse
import asyncio
from bson import ObjectId

from app.database import Database
from app.models.queue_item import QueueItemStatus
from app.services.external_api import enrich_queue_item
from app.services.queue import QueueService


async def main(limit_per_room: int, room_id: str | None) -> None:
    """Backfill provider metadata for existing queued items."""
    await Database.connect()
    try:
        db = Database.get_db()
        queue_service = QueueService(db)

        room_query = {"_id": ObjectId(room_id)} if room_id and ObjectId.is_valid(room_id) else {}
        room_cursor = db.rooms.find(room_query, {"members": 1})
        updated = 0

        async for room in room_cursor:
            member_regions = [
                (member.get("region") or "US").strip().upper()
                for member in room.get("members", [])
                if member.get("region") or member.get("user_id")
            ]

            queue_items = await queue_service.get_room_queue(
                str(room["_id"]),
                status=QueueItemStatus.QUEUED,
                limit=limit_per_room,
            )

            for item in queue_items:
                if item.providers_by_region:
                    continue

                enrichment = await enrich_queue_item(
                    item.title,
                    tmdb_id=item.tmdb_id,
                    member_regions=member_regions,
                )
                if not enrichment:
                    continue

                await queue_service.enrich_item(
                    item.id,
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
                updated += 1

        print(f"Provider backfill complete. Updated {updated} queue item(s).")
    finally:
        await Database.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-per-room", type=int, default=200)
    parser.add_argument("--room-id", type=str, default=None)
    args = parser.parse_args()
    asyncio.run(main(args.limit_per_room, args.room_id))

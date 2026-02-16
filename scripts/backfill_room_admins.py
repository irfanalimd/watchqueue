"""Backfill missing room admin ownership and member regions."""

import asyncio

from app.database import Database


async def main() -> None:
    """Run room admin/member-region migration and exit."""
    await Database.connect()
    try:
        # Connect already runs migrations, but we invoke again for explicit CLI usage.
        await Database.run_migrations()
        print("Room admin and member-region backfill completed.")
    finally:
        await Database.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

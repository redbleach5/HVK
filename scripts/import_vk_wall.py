"""Import the full public wall. Prints counts only."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402
from app.memory.ingest import reindex_posts  # noqa: E402
from app.memory.store import MemoryStore  # noqa: E402
from app.vk.client import import_wall_posts  # noqa: E402


async def main() -> None:
    get_settings.cache_clear()
    await init_db()
    async with SessionLocal() as session:
        n = await import_wall_posts(session, with_comments=True)
        await reindex_posts(session)
        posts = await MemoryStore(session).count_posts()
    print("imported", n)
    print("posts_in_db", posts)


if __name__ == "__main__":
    asyncio.run(main())

# -*- coding: utf-8 -*-
"""Сколько авторских постов и где провальные в порядке вовлечённости."""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import desc, select

from app.db.models import Post
from app.db.session import SessionLocal
from app.memory.store import _is_author_text


async def main() -> int:
    async with SessionLocal() as session:
        rows = (
            (await session.execute(select(Post).order_by(desc(Post.engagement), desc(Post.id))))
            .scalars().all()
        )
        pool = [p for p in rows if _is_author_text(p)]
        print(f"авторских постов всего: {len(pool)}")
        ids = {112, 22, 26, 15, 98, 104, 108, 40, 45}
        for rank, p in enumerate(pool, start=1):
            if p.id in ids:
                print(f"  #{p.id}: rank по вовлечённости {rank}, eng={p.engagement}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

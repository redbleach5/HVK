# -*- coding: utf-8 -*-
"""Связь провала самопоиска с длиной поста (e5 размывает длинные тексты)."""
import asyncio
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import desc, select

import app.memory.retrieve as retrieve
from app.db.models import Post
from app.db.session import SessionLocal
from app.memory.retrieve import posts_for_query
from app.memory.store import _is_author_text

SAMPLE = 15


async def main() -> int:
    real_search = retrieve.search_posts
    async with SessionLocal() as session:
        rows = (
            (await session.execute(select(Post).order_by(desc(Post.id)))).scalars().all()
        )
        pool = [p for p in rows if _is_author_text(p) and (p.text or "").strip()]
        rng = random.Random(31)
        sample = rng.sample(pool, min(SAMPLE, len(pool)))
        for post in sample:
            q = " ".join((post.text or "").split())[:140]
            sem = await asyncio.to_thread(real_search, q, 10)
            ranks = {int(h["post_id"]): i for i, h in enumerate(sem, start=1)}
            fused = await posts_for_query(session, q, limit=6)
            fused_ids = [p.id for p in fused[:3]]
            ok = post.id in fused_ids
            mark = "OK " if ok else "FAIL"
            d = ranks.get(post.id)
            dist = (
                round(float(sem[d - 1]["distance"]), 3) if d else None
            )
            print(
                f"{mark} #{post.id:4d} len={len(post.text or ''):5d} "
                f"e5_rank={d if d else '—'} self_dist={dist}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

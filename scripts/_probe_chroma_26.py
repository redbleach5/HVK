# -*- coding: utf-8 -*-
"""Есть ли пост#26 в Chroma-индексе и что e5 думает о его тексте."""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import select

from app.db.models import Post
from app.db.session import SessionLocal
from app.memory.chroma import search_posts


async def main() -> int:
    async with SessionLocal() as session:
        p = await session.get(Post, 26)
        text = " ".join((p.text or "").split())
        print(f"пост#26 в базе, {len(text)} симв., eng={p.engagement}")
        print("текст:", text[:160])
        hits = await asyncio.to_thread(search_posts, text[:140], 20)
        ids = [(int(h["post_id"]), round(float(h.get("distance") or -1), 3)) for h in hits]
        print("e5 top-20:", ids)
        print("пост#26 в выдаче:", 26 in [i for i, _ in ids])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

# -*- coding: utf-8 -*-
"""Где пост с «рецепт» и почему он не входит в top-6 проектного вопроса."""
from __future__ import annotations

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

import app.memory.retrieve as retrieve
from app.db.models import Post
from app.db.session import SessionLocal
from app.memory.chroma import search_posts
from app.memory.retrieve import _keys, posts_for_query
from app.memory.store import _is_author_text
from app.memory.themes import is_promotional

QUESTION = (
    "Кажется, я уже писала про осенний гардероб и мамин рецепт. "
    "Что лучше выложить в сообщество сейчас, чтобы не повторяться?"
)


async def main() -> int:
    async with SessionLocal() as session:
        rows = (
            (await session.execute(select(Post).order_by(desc(Post.id)))).scalars().all()
        )
        recipe = [
            p
            for p in rows
            if "рецеп" in (p.text or "").lower() or "рецеп" in (p.theme or "").lower()
        ]
        print(f"постов со словом «рецепт*»: {len(recipe)}")
        for p in recipe:
            text = (p.text or "").strip()
            print(
                f"  #{p.id} len={len(text)} eng={p.engagement} авторский={_is_author_text(p)} "
                f"промо={is_promotional(text)} тема={p.theme!r}"
            )
            print("    ", " ".join(text.split())[:120])
        fused = await posts_for_query(session, QUESTION, limit=6)
        print("фьюжн top-6:", [p.id for p in fused])
        sem = await asyncio.to_thread(search_posts, QUESTION, 6)
        print("семантика top-6:", [(h["post_id"], round(float(h["distance"] or 9), 3)) for h in sem])
        qkeys = _keys(QUESTION)
        print("ключи запроса:", sorted(qkeys))
        for p in recipe[:3]:
            ov = qkeys & _keys(p.text or "")
            print(f"  #{p.id} пересечение ключей: {sorted(ov)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

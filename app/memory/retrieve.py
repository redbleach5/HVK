"""Нужные посты к вопросу: векторный поиск + слова, не весь архив оптом."""

from __future__ import annotations

import asyncio
import logging
import re

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Post
from app.memory.chroma import search_posts
from app.memory.store import _is_author_text

logger = logging.getLogger(__name__)

_WORD = re.compile(r"[а-яёa-z]{4,}", re.IGNORECASE)


async def posts_for_query(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 6,
) -> list[Post]:
    """Посты к этому сообщению: смысл + слова, рекламу выкидываем."""
    limit = max(1, min(limit, 12))
    scored: dict[int, tuple[float, Post]] = {}

    def add(post: Post | None, score: float) -> None:
        if post is None or not _is_author_text(post):
            return
        prev = scored.get(post.id)
        if prev is None or score > prev[0]:
            scored[post.id] = (score, post)
        elif prev is not None:
            scored[post.id] = (prev[0] + score * 0.35, prev[1])

    q = (query or "").strip()
    if q:
        try:
            raw = await asyncio.to_thread(search_posts, q, limit + 8)
        except Exception:
            logger.exception("Поиск по архиву не удался — иду по словам")
            raw = []
        for hit in raw:
            post = await session.get(Post, int(hit.get("post_id") or 0))
            dist = hit.get("distance")
            if dist is None:
                semantic = 3.0
            else:
                semantic = max(0.0, 2.2 - float(dist)) * 4.0
            add(post, semantic)

    for post in await _keyword_posts(session, q, limit=max(limit * 4, 16)):
        words = _WORD.findall(q.lower())
        blob = (post.text or "").lower()
        overlap = sum(1 for word in words if word in blob) if words else 1
        add(post, overlap * 8.0 + min(float(post.engagement or 0), 80.0) / 40.0)

    ranked = sorted(scored.values(), key=lambda item: -item[0])
    return [post for _, post in ranked[:limit]]


async def _keyword_posts(session: AsyncSession, query: str, *, limit: int) -> list[Post]:
    words = _WORD.findall((query or "").lower())
    result = await session.execute(
        select(Post).order_by(desc(Post.engagement), desc(Post.id)).limit(120)
    )
    rows = [p for p in result.scalars() if _is_author_text(p)]
    if not words:
        return rows[:limit]
    scored: list[tuple[int, float, Post]] = []
    for post in rows:
        blob = (post.text or "").lower()
        score = sum(1 for word in words if word in blob)
        if score:
            scored.append((score, float(post.engagement or 0), post))
    scored.sort(key=lambda item: (-item[0], -item[1]))
    return [item[2] for item in scored[:limit]]

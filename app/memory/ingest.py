"""Сохранение вставленных постов в SQLite и векторный архив."""

from __future__ import annotations

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AudienceCache, Post
from app.memory.chroma import upsert_post
from app.memory.store import _is_author_text

logger = logging.getLogger(__name__)


def _meta(post: Post, *, source: str) -> dict:
    return {
        "source": source,
        "theme": post.theme or "",
        "engagement": float(post.engagement or 0),
        "published_at": post.published_at.isoformat() if post.published_at else "",
    }


async def _invalidate_audience_cache(session: AsyncSession) -> None:
    """Любое изменение архива обесценивает кэш аудит-отчёта."""
    await session.execute(delete(AudienceCache))


async def reindex_posts(session: AsyncSession) -> int:
    """Перекладывает все тексты архива в Chroma. Идемпотентно."""
    result = await session.execute(select(Post).where(Post.text != ""))
    count = 0
    for post in result.scalars():
        text = (post.text or "").strip()
        if not text or not _is_author_text(post):
            continue
        source = "vk" if post.vk_post_id else "paste"
        upsert_post(post.id, text, _meta(post, source=source))
        count += 1
    if count:
        await _invalidate_audience_cache(session)
    logger.info("Индекс архива: %s постов", count)
    return count


async def save_pasted_posts(session: AsyncSession, texts: list[str]) -> int:
    """Пишет новые посты в базу и сразу в индекс. Дубликаты по тексту пропускает."""
    existing = await session.execute(select(Post.text))
    have = {(row or "").strip() for row in existing.scalars() if (row or "").strip()}

    added: list[Post] = []
    for raw in texts:
        text = (raw or "").strip()
        if not text or text in have:
            continue
        post = Post(text=text)
        session.add(post)
        added.append(post)
        have.add(text)

    if not added:
        return 0

    await session.flush()
    for post in added:
        upsert_post(post.id, post.text or "", _meta(post, source="paste"))
    await _invalidate_audience_cache(session)
    return len(added)

"""Архив: векторный поиск и предложение переиспользовать старый контент."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import ensure_why, related_post_labels
from app.context.engine import current_season, format_date_ru
from app.db.models import Post
from app.memory.chroma import search_posts, similar_to_post
from app.schemas.agents import ArchiveHit, ArchiveSearchResult
from app.schemas.common import WhyBlock

logger = logging.getLogger(__name__)


async def search_archive(
    session: AsyncSession,
    query: str,
    *,
    n_results: int = 5,
) -> ArchiveSearchResult:
    """Ищет посты по смыслу и обогащает их данными из SQLite."""
    hits_raw = search_posts(query, n_results=n_results)
    hits: list[ArchiveHit] = []
    for raw in hits_raw:
        post = await session.get(Post, raw["post_id"])
        meta = raw.get("metadata") or {}
        published = None
        theme = None
        engagement = 0.0
        preview = (raw.get("text") or "")[:220]
        if post:
            published = post.published_at.isoformat() if post.published_at else None
            theme = post.theme
            engagement = post.engagement
            preview = (post.text or preview)[:220]
        else:
            published = meta.get("published_at")
            theme = meta.get("theme")
            engagement = float(meta.get("engagement") or 0)

        hits.append(
            ArchiveHit(
                post_id=raw["post_id"],
                text_preview=preview,
                published_at=published,
                theme=theme,
                engagement=engagement,
                why_relevant=f"Близко по смыслу к запросу «{query[:80]}»",
            )
        )

    labels = await related_post_labels(session)
    why = ensure_why(
        WhyBlock(
            summary=f"Нашла {len(hits)} отголосков в архиве по запросу",
            related_posts=labels,
            seasonality=f"Сейчас {format_date_ru()}, сезон — {current_season()}",
            audience_pattern="Старый пост может снова откликнуться в похожем сезоне",
        ),
        "Поиск по архиву",
    )
    logger.info("Архив: query=%r hits=%s", query[:60], len(hits))
    return ArchiveSearchResult(hits=hits, why=why)


async def find_similar(
    session: AsyncSession,
    post_id: int,
    *,
    n_results: int = 5,
) -> ArchiveSearchResult:
    """Ищет посты, похожие на уже известный."""
    raw_hits = similar_to_post(post_id, n_results=n_results)
    # Переиспользуем search_archive-логику через обогащение
    fake_query = f"похожие на пост {post_id}"
    # вручную соберём как в search
    hits: list[ArchiveHit] = []
    for raw in raw_hits:
        post = await session.get(Post, raw["post_id"])
        preview = (raw.get("text") or "")[:220]
        published = None
        theme = None
        engagement = 0.0
        if post:
            published = post.published_at.isoformat() if post.published_at else None
            theme = post.theme
            engagement = post.engagement
            preview = (post.text or preview)[:220]
        hits.append(
            ArchiveHit(
                post_id=raw["post_id"],
                text_preview=preview,
                published_at=published,
                theme=theme,
                engagement=engagement,
                why_relevant=f"Похож на пост #{post_id}",
            )
        )
    why = ensure_why(
        WhyBlock(
            summary=f"Похожие на пост #{post_id}",
            seasonality=f"Сейчас {format_date_ru()}, сезон — {current_season()}",
        ),
        fake_query,
    )
    return ArchiveSearchResult(hits=hits, why=why)


async def seasonal_reuse_suggestions(
    session: AsyncSession,
    *,
    n_results: int = 4,
) -> ArchiveSearchResult:
    """Предлагает переиспользовать старый контент, актуальный в текущем сезоне."""
    season = current_season()
    month = datetime.now().strftime("%B")
    query = f"{season} дом уют ритуал {month}"
    return await search_archive(session, query, n_results=n_results)

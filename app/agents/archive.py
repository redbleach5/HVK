"""Архив: векторный поиск и предложение переиспользовать старый контент."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import ensure_why
from app.context.engine import current_season, format_date_ru
from app.db.models import Post
from app.memory.archive import Archive
from app.memory.citations import post_citation
from app.schemas.agents import ArchiveHit, ArchiveSearchResult
from app.schemas.common import WhyBlock

logger = logging.getLogger(__name__)


def _hit(post: Post, why_relevant: str) -> ArchiveHit:
    published = post.published_at.isoformat() if post.published_at else None
    preview = (post.text or "")[:220]
    return ArchiveHit(
        post_id=post.id,
        text_preview=preview,
        published_at=published,
        theme=post.theme,
        engagement=float(post.engagement or 0),
        why_relevant=why_relevant,
    )


async def search_archive(
    session: AsyncSession,
    query: str,
    *,
    n_results: int = 5,
) -> ArchiveSearchResult:
    """Ищет посты по смыслу через библиотеку архива."""
    posts = await Archive(session).similar(query, limit=n_results)
    hits = [_hit(p, f"Близко по смыслу к запросу «{query[:80]}»") for p in posts]
    labels = [post_citation(p) for p in posts[:6] if (p.text or "").strip()]
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
    archive = Archive(session)
    source = await archive.get(post_id)
    if source is None or not (source.text or "").strip():
        why = ensure_why(None, f"Пост #{post_id} не в живом архиве")
        return ArchiveSearchResult(hits=[], why=why)
    posts = [
        p
        for p in await archive.similar(source.text or "", limit=n_results + 1)
        if p.id != post_id
    ][:n_results]
    hits = [_hit(p, f"Похож на пост #{post_id}") for p in posts]
    why = ensure_why(
        WhyBlock(
            summary=f"Похожие на пост #{post_id}",
            related_posts=[post_citation(p) for p in posts[:4]],
            seasonality=f"Сейчас {format_date_ru()}, сезон — {current_season()}",
        ),
        f"похожие на пост {post_id}",
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

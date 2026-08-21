"""Общие хелперы агентов: промпт, suggestion, WhyBlock."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.context.engine import ContextEngine, current_season, format_date_ru
from app.db.models import Suggestion
from app.memory.store import MemoryStore
from app.schemas.common import WhyBlock

SYSTEM_ASSISTANT = (
    "Ты — «Тихая редакция», рабочий ассистент автора лайфстайл-блога "
    "«Красивое в обычном». Не пиши посты за автора и не выдумывай факты. "
    "Предложения сопровождай кратким «почему». Тон прямой, без рекламного крика."
)


async def build_agent_context(session: AsyncSession, *, extra: str = "") -> str:
    """Собирает контекст + память для промпта агента."""
    return await ContextEngine(session).build(extra=extra)


def ensure_why(why: WhyBlock | dict[str, Any] | None, fallback: str) -> WhyBlock:
    """Гарантирует валидный WhyBlock даже при урезанном ответе модели."""
    if isinstance(why, WhyBlock):
        if not why.summary:
            why.summary = fallback
        if not why.seasonality:
            why.seasonality = f"Сейчас {format_date_ru()}, сезон — {current_season()}"
        return why
    if isinstance(why, dict):
        data = dict(why)
        data.setdefault("summary", fallback)
        data.setdefault("related_posts", [])
        data.setdefault(
            "seasonality",
            f"Сейчас {format_date_ru()}, сезон — {current_season()}",
        )
        return WhyBlock.model_validate(data)
    return WhyBlock(
        summary=fallback,
        seasonality=f"Сейчас {format_date_ru()}, сезон — {current_season()}",
    )


async def save_agent_suggestion(
    session: AsyncSession,
    *,
    kind: str,
    title: str,
    payload: dict[str, Any],
    why: WhyBlock,
    parent_id: int | None = None,
    log_action: str | None = None,
    log_summary: str | None = None,
) -> Suggestion:
    """Пишет предложение в память и опционально в историю действий."""
    memory = MemoryStore(session)
    suggestion = await memory.save_suggestion(
        kind=kind,
        title=title,
        payload=payload,
        why=why.model_dump(),
        parent_id=parent_id,
    )
    if log_action and log_summary:
        await memory.log(log_action, log_summary, {"suggestion_id": suggestion.id})
    return suggestion


async def related_post_labels(session: AsyncSession, limit: int = 3) -> list[str]:
    """Короткие подписи недавних/топ постов для WhyBlock."""
    memory = MemoryStore(session)
    posts = await memory.top_posts(45, limit) or await memory.recent_posts(limit)
    labels: list[str] = []
    for post in posts:
        date = post.published_at.strftime("%d.%m") if post.published_at else "без даты"
        theme = post.theme or (post.text or "")[:40] or "пост"
        labels.append(f"{date}: {theme}")
    return labels

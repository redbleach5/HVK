"""Обратная связь автора → урок в память."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Suggestion
from app.memory.store import MemoryStore

logger = logging.getLogger(__name__)


async def apply_feedback(
    session: AsyncSession,
    suggestion_id: int,
    accepted: bool,
    note: str = "",
) -> Suggestion:
    """Принимает или отклоняет предложение и записывает урок.

    Принятое усиливает предпочтения. Отклонённое уходит в антипатии,
    чтобы система не предлагала то же самое снова.
    """
    suggestion = await session.get(Suggestion, suggestion_id)
    if suggestion is None:
        raise KeyError(f"предложение {suggestion_id} не найдено")

    suggestion.status = "accepted" if accepted else "rejected"
    suggestion.feedback_note = note
    suggestion.decided_at = datetime.utcnow()

    memory = MemoryStore(session)
    title = suggestion.title or suggestion.kind
    why = note or (suggestion.why or {}).get("summary") or "автор не пояснила, но выбор важен"
    if accepted:
        await memory.add_lesson(
            title=f"Откликнулось: {title}",
            outcome="success",
            why=why,
            source="feedback",
            suggestion_id=suggestion.id,
        )
        kind_map = {
            "chat": "themes",
            "idea": "themes",
            "photo_advice": "photo",
            "edit": "style",
            "audience": "audience",
        }
        pref_kind = kind_map.get(suggestion.kind, suggestion.kind)
        await memory.add_preference(pref_kind, title[:120], why, weight=1.2)
        await memory.log("feedback", f"Учла совет: {title}")
    else:
        await memory.add_lesson(
            title=f"Не зашло: {title}",
            outcome="fail",
            why=why,
            source="feedback",
            suggestion_id=suggestion.id,
        )
        await memory.add_antipathy(title, why, days=40)
        await memory.log("feedback", f"Не согласилась: {title}")

    await session.commit()
    await session.refresh(suggestion)
    logger.info("Фидбек по suggestion=%s: %s", suggestion_id, suggestion.status)
    return suggestion

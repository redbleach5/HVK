"""Консьерж ЛС: классификация и черновик ответа. Ничего не отправляет."""

from __future__ import annotations

import logging

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import (
    SYSTEM_ASSISTANT,
    ensure_why,
    pack_for_agent,
    save_agent_suggestion,
)
from app.llm.client import get_llm
from app.llm.exceptions import EmptyArchiveError
from app.memory.archive import Archive
from app.memory.store import MemoryStore
from app.schemas.agents import ConciergeReply
from app.schemas.common import WhyBlock

logger = logging.getLogger(__name__)

_CATEGORY_LABELS = {
    "ad": "реклама",
    "product_question": "вопрос о товаре",
    "compliment": "комплимент",
    "other": "другое",
}


class _ConciergeLlmOut(BaseModel):
    category: str
    category_label: str = ""
    related_post: str | None = None
    draft_reply: str
    why: WhyBlock


async def draft_dm_reply(session: AsyncSession, message_text: str) -> ConciergeReply:
    """Классифицирует входящее ЛС и готовит черновик ответа автору."""
    if await MemoryStore(session).count_author_posts() == 0:
        raise EmptyArchiveError("no posts")
    context, labels = await pack_for_agent(
        session, query=message_text, with_session=False
    )
    similar = await Archive(session).similar(message_text, limit=3)
    archive_block = "\n".join(
        f"- пост #{p.id}: {(p.text or '')[:180]}"
        for p in similar
    ) or "- в архиве пока ничего похожего"

    system = (
        f"{SYSTEM_ASSISTANT}\n"
        "Ты консьерж личных сообщений. Сам ничего не отправляешь. "
        "Классифицируй сообщение (ad | product_question | compliment | other), "
        "найди связанный пост если есть, и подготовь тёплый черновик ответа от автора. "
        "Без продаж и без обещаний, которых нет в данных."
    )
    user = f"""{context}

Похожие посты из архива:
{archive_block}

Входящее сообщение:
{message_text}

Верни JSON: category, category_label, related_post, draft_reply, why.
"""

    parsed = await get_llm().complete_json(
        system=system,
        user=user,
        schema=_ConciergeLlmOut,
        temperature=0.35,
        label="concierge",
    )
    category = parsed.category if parsed.category in _CATEGORY_LABELS else "other"
    label = parsed.category_label or _CATEGORY_LABELS[category]
    why = ensure_why(parsed.why, "Черновик по тону блога и похожим постам")
    if not why.related_posts:
        why.related_posts = labels

    suggestion = await save_agent_suggestion(
        session,
        kind="concierge",
        title=f"ЛС: {label}",
        payload={"message": message_text, "draft": parsed.draft_reply, "category": category},
        why=why,
        log_action="concierge",
        log_summary=f"Черновик ответа ({label})",
    )
    await session.commit()

    reply = ConciergeReply(
        category=category,  # type: ignore[arg-type]
        category_label=label,
        related_post=parsed.related_post,
        draft_reply=parsed.draft_reply,
        why=why,
        suggestion_id=suggestion.id,
    )
    logger.info("Консьерж suggestion=%s category=%s", suggestion.id, category)
    return reply

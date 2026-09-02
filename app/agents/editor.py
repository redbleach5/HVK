"""Редактор текста: правит черновик, сохраняя голос автора."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import (
    SYSTEM_ASSISTANT,
    ensure_why,
    pack_for_agent,
    save_agent_suggestion,
)
from app.llm.client import get_llm
from app.llm.exceptions import EmptyArchiveError
from app.memory.store import MemoryStore
from app.schemas.agents import EditorResult, TextEdit
from app.schemas.common import WhyBlock
from app.voice.detector import detect_voice

logger = logging.getLogger(__name__)


class _EditLlmOut(BaseModel):
    """Сырой ответ редактора."""

    revised_text: str
    edits: list[TextEdit] = Field(default_factory=list)
    alternative_openings: list[str] = Field(default_factory=list)
    why: WhyBlock


async def edit_draft(
    session: AsyncSession,
    draft: str,
    *,
    topic_hint: str = "",
) -> EditorResult:
    """Редактирует черновик без смены смысла и без «украшательства» ценой искренности.

    Учится на отвергнутых правках: последние N «не зашло» по стилю
    подмешиваются в промпт как «чего автору не подходит».
    Так редактор не повторяет rejected-стиль через 2 недели.
    """
    memory = MemoryStore(session)
    if await memory.count_author_posts() == 0:
        raise EmptyArchiveError("no posts")
    context, labels = await pack_for_agent(
        session, query=draft, with_session=False, include_voice=False
    )
    voice = await memory.latest_voice()
    voice_profile = voice.profile if voice else {}
    snippets = []
    for post in await memory.recent_posts(4):
        body = (post.text or "").strip().replace("\n", " ")[:180]
        snippets.append(f"— {post.theme or 'пост'}: {body}")
    archive_note = "\n".join(snippets) or "архива нет — не ссылайся на несуществующие посты"
    if not voice_profile:
        archive_note += "\nпрофиля голоса ещё нет — правь бережно, без чужого тона"

    system = (
        f"{SYSTEM_ASSISTANT}\n"
        "Ты редактор текста. Сохраняй голос автора. Не меняй смысл, "
        "не добавляй фактов, не делай текст «красивее» за счёт искренности. "
        "Не повторяй стиль из «Чего не подходит в правках» в памяти. "
        "Верни revised_text, список правок (original, revised, explanation), "
        "2–3 alternative_openings и why."
    )
    user = f"""{context}

Профиль голоса:
{voice_profile or "ещё не собран"}

Её тексты (ритм и лексика, не копируй оптом):
{archive_note}

Тема (если есть): {topic_hint or "не указана"}

Черновик:
{draft}
"""

    parsed = await get_llm().complete_json(
        system=system,
        user=user,
        schema=_EditLlmOut,
        temperature=0.50,
        max_tokens=2400,
        label="editor",
    )
    voice_check = await detect_voice(session, parsed.revised_text, topic_hint=topic_hint)

    why = ensure_why(parsed.why, "Правки бережные, чтобы текст оставался в голосе автора")
    why.related_posts = labels

    parent = await save_agent_suggestion(
        session,
        kind="edit",
        title="Редактура черновика",
        payload={
            "draft": draft,
            "revised_text": parsed.revised_text,
            "topic_hint": topic_hint,
        },
        why=why,
        log_action="text",
        log_summary="Отредактировала черновик",
    )

    edits: list[TextEdit] = []
    for edit in parsed.edits:
        child = await save_agent_suggestion(
            session,
            kind="edit",
            title=(edit.explanation or edit.revised)[:200],
            payload=edit.model_dump(),
            why=why,
            parent_id=parent.id,
        )
        edits.append(
            TextEdit(
                original=edit.original,
                revised=edit.revised,
                explanation=edit.explanation,
                suggestion_id=child.id,
            )
        )

    await session.commit()

    result = EditorResult(
        revised_text=parsed.revised_text,
        edits=edits,
        alternative_openings=parsed.alternative_openings,
        in_voice=voice_check.in_voice,
        voice_notes=voice_check.what_stands_out,
        why=why,
        suggestion_id=parent.id,
    )
    logger.info("Редактура suggestion=%s, правок=%s", parent.id, len(edits))
    return result

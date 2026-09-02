"""Генератор идей с учётом сезона, памяти и anti-repeat."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import (
    SYSTEM_JSON,
    ensure_why,
    pack_for_agent,
    save_agent_suggestion,
)
from app.db.models import Idea
from app.llm.client import get_llm
from app.llm.exceptions import EmptyArchiveError
from app.memory.store import MemoryStore
from app.schemas.agents import IdeaBatch, IdeaCard
from app.schemas.common import WhyBlock, WhyBlockLlm

logger = logging.getLogger(__name__)


class _IdeaCardLlm(BaseModel):
    theme: str
    format: str = ""
    description: str = ""
    personal_angle: str = ""
    visual: str = ""
    effort: str = "medium"
    why_now: str = ""
    why: WhyBlockLlm = Field(default_factory=WhyBlockLlm)


class _IdeaBatchLlm(BaseModel):
    ideas: list[_IdeaCardLlm] = Field(default_factory=list)


def idea_row_to_card(idea: Idea) -> IdeaCard:
    """Карточка из уже сохранённой идеи — без вызова модели."""
    effort = idea.effort if idea.effort in ("light", "medium", "deep") else "medium"
    return IdeaCard(
        theme=idea.theme,
        format=idea.format or "",
        description=idea.description or "",
        personal_angle=idea.personal_angle or "",
        visual=idea.visual or "",
        effort=effort,  # type: ignore[arg-type]
        why_now=idea.why_now or "",
        why=WhyBlock(summary=idea.why_now or "Из сохранённых идей"),
        id=idea.id,
        suggestion_id=idea.suggestion_id,
    )


async def generate_ideas(session: AsyncSession, count: int = 3) -> IdeaBatch:
    """Генерирует пачку идей, не повторяя недавнее и антипатии.

    Двухслойная фильтрация против повторов:
    1. Строковая: точное совпадение темы с недавними идеями и antipathy (быстро).
    2. Семантическая: проверка каждой темы через ChromaDB-эмбеддинги против antipathy.
       Ловит «Утренний чай» когда отвергнута «Завтрак с чаем» — точное совпадение этого не видит.

    Если после фильтрации осталось меньше, чем просили — генератор дособирает ещё
    (один повторный вызов с явным списком «уже предложенных» тем).
    """
    count = max(1, min(count, 6))
    memory = MemoryStore(session)
    if await memory.count_author_posts() == 0:
        raise EmptyArchiveError("no posts")
    recent_themes = await memory.recent_idea_themes(20)
    anti = await memory.antipathy_topics()
    recent4_ids = {p.id for p in await memory.recent_posts(4)}
    snippets = []
    for post in await memory.recent_posts(6):
        if post.id in recent4_ids:
            continue  # краткие превью этих постов уже в контексте — не дублируем
        theme = post.theme or "без темы"
        body = (post.text or "").strip().replace("\n", " ")[:220]
        snippets.append(f"— {theme}: {body}")
    archive_block = "\n".join(snippets) or "(пусто)"
    context, labels = await pack_for_agent(
        session,
        with_session=False,
        extra=(
            f"Недавние темы идей (не повторять): {', '.join(recent_themes) or 'нет'}\n"
            f"Антипатии: {', '.join(anti) or 'нет'}\n"
            f"Архив автора (опирайся только на это, цитируй в why.related_posts):\n{archive_block}"
        ),
    )

    system = (
        f"{SYSTEM_JSON}\n"
        "Ты генератор идей для личного лайфстайл-блога. "
        "Каждая идея — с личным углом автора, визуальным направлением, "
        "оценкой усилия (light|medium|deep) и why_now. Не повторяй недавнее."
    )

    already_suggested: list[str] = []
    cards: list[IdeaCard] = []

    for attempt in range(2):
        remaining = count - len(cards)
        if remaining <= 0:
            break
        if attempt > 0 and cards:
            break

        if attempt > 0:
            # Повторный вызов с явным списком «уже предложенных» — чтобы не дублировать
            extra_note = (
                f"\n\nУже предложено в этом вызове (не повторяй даже близко по смыслу):\n"
                + "\n".join(f"- {t}" for t in already_suggested)
            )
        else:
            extra_note = ""

        user = f"""{context}

Нужно ровно {remaining} идей. Верни JSON: {{ "ideas": [ ... ] }}.
У каждой: theme, format, description, personal_angle, visual, effort, why_now, why.
why.related_posts — короткие отсылки к её реальным постам из архива, не выдуманным.
Не предлагай то, чего нет в её текстах.{extra_note}
"""
        try:
            parsed = await get_llm().complete_json(
                system=system,
                user=user,
                schema=_IdeaBatchLlm,
                temperature=0.55 if attempt == 0 else 0.65,
                max_tokens=min(2200, 450 + remaining * 480),
                label="ideas",
            )
        except Exception:
            logger.exception("generate_ideas: LLM failed on attempt %s", attempt + 1)
            continue

        for raw in parsed.ideas[:remaining]:
            theme = (raw.theme or "").strip()
            if not theme:
                continue

            # Строковая проверка против уже принятых в этом вызове
            if theme.lower() in {t.lower() for t in already_suggested}:
                continue

            # Семантическая проверка против antipathy
            blocked, matched = await memory.is_semantically_blocked(theme)
            if blocked:
                logger.info(
                    "Идея «%s» отфильтрована: семантически близка к antipathy «%s»",
                    theme, matched,
                )
                continue

            effort = raw.effort if raw.effort in ("light", "medium", "deep") else "medium"
            why = ensure_why(raw.why.model_dump(), raw.why_now or "Подходит к сезону и ритму блога")
            why.related_posts = labels

            suggestion = await save_agent_suggestion(
                session,
                kind="idea",
                title=theme[:200],
                payload=raw.model_dump(),
                why=why,
            )
            idea = Idea(
                suggestion_id=suggestion.id,
                theme=theme,
                format=raw.format,
                description=raw.description,
                personal_angle=raw.personal_angle,
                visual=raw.visual,
                effort=effort,
                why_now=raw.why_now,
                status="new",
            )
            session.add(idea)
            await session.flush()

            cards.append(
                IdeaCard(
                    theme=theme,
                    format=raw.format,
                    description=raw.description,
                    personal_angle=raw.personal_angle,
                    visual=raw.visual,
                    effort=effort,  # type: ignore[arg-type]
                    why_now=raw.why_now,
                    why=why,
                    id=idea.id,
                    suggestion_id=suggestion.id,
                )
            )
            already_suggested.append(theme)

    await memory.log("ideas", f"Предложила {len(cards)} идей (попыток: {attempt + 1})")
    await session.commit()
    logger.info("Сгенерировано идей: %s (попыток: %s)", len(cards), attempt + 1)
    return IdeaBatch(ideas=cards)

"""Генератор идей с учётом сезона, памяти и anti-repeat."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import (
    SYSTEM_ASSISTANT,
    build_agent_context,
    ensure_why,
    related_post_labels,
    save_agent_suggestion,
)
from app.db.models import Idea
from app.llm.client import get_llm
from app.llm.exceptions import EmptyArchiveError
from app.memory.store import MemoryStore
from app.schemas.agents import IdeaBatch, IdeaCard
from app.schemas.common import WhyBlock

logger = logging.getLogger(__name__)


class _IdeaCardLlm(BaseModel):
    theme: str
    format: str = ""
    description: str = ""
    personal_angle: str = ""
    visual: str = ""
    effort: str = "medium"
    why_now: str = ""
    why: WhyBlock


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
    """Генерирует пачку идей, не повторяя недавнее и антипатии."""
    count = max(1, min(count, 6))
    memory = MemoryStore(session)
    if await memory.count_posts() == 0:
        raise EmptyArchiveError("no posts")
    recent_themes = await memory.recent_idea_themes(20)
    anti = await memory.antipathy_topics()
    snippets = []
    for post in await memory.recent_posts(6):
        theme = post.theme or "без темы"
        body = (post.text or "").strip().replace("\n", " ")[:220]
        snippets.append(f"— {theme}: {body}")
    archive_block = "\n".join(snippets) or "(пусто)"
    context = await build_agent_context(
        session,
        extra=(
            f"Недавние темы идей (не повторять): {', '.join(recent_themes) or 'нет'}\n"
            f"Антипатии: {', '.join(anti) or 'нет'}\n"
            f"Архив автора (опирайся только на это, цитируй в why.related_posts):\n{archive_block}"
        ),
    )
    labels = await related_post_labels(session)

    system = (
        f"{SYSTEM_ASSISTANT}\n"
        "Ты генератор идей для личного лайфстайл-блога. "
        "Каждая идея — с личным углом автора, визуальным направлением, "
        "оценкой усилия (light|medium|deep) и why_now. Не повторяй недавнее."
    )
    user = f"""{context}

Нужно ровно {count} идей. Верни JSON: {{ "ideas": [ ... ] }}.
У каждой: theme, format, description, personal_angle, visual, effort, why_now, why.
why.related_posts — короткие отсылки к её реальным постам из архива, не выдуманным.
Не предлагай то, чего нет в её текстах.
"""

    parsed = await get_llm().complete_json(
        system=system,
        user=user,
        schema=_IdeaBatchLlm,
        temperature=0.55,
        max_tokens=3500,
    )

    cards: list[IdeaCard] = []
    for raw in parsed.ideas[:count]:
        effort = raw.effort if raw.effort in ("light", "medium", "deep") else "medium"
        why = ensure_why(raw.why, raw.why_now or "Подходит к сезону и ритму блога")
        why.related_posts = labels

        suggestion = await save_agent_suggestion(
            session,
            kind="idea",
            title=raw.theme[:200],
            payload=raw.model_dump(),
            why=why,
        )
        idea = Idea(
            suggestion_id=suggestion.id,
            theme=raw.theme,
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
                theme=raw.theme,
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

    await memory.log("ideas", f"Предложила {len(cards)} идей")
    await session.commit()
    logger.info("Сгенерировано идей: %s", len(cards))
    return IdeaBatch(ideas=cards)

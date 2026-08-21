"""Вкладка «Сегодня» — утреннее резюме."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.ideas import generate_ideas
from app.context.engine import format_date_ru, current_season
from app.db.models import Idea
from app.db.session import get_session
from app.llm.exceptions import ModelAsleepError
from app.memory.store import MemoryStore
from app.schemas.api import TodayResponse
from app.schemas.agents import IdeaCard
from app.schemas.common import ActivityItem, WhyBlock

router = APIRouter(tags=["today"])


@router.get("/today", response_model=TodayResponse)
async def today(session: AsyncSession = Depends(get_session)) -> TodayResponse:
    """Тихое резюме: дайджест, идеи, напоминания плана, история."""
    memory = MemoryStore(session)
    digest_row = await memory.latest_digest()
    plan = await memory.open_plan_items()
    activity = await memory.recent_activity(8)
    top = await memory.top_posts(21, 3)

    if digest_row:
        body = digest_row.body
        highlights = digest_row.highlights or []
        idea_ids = digest_row.idea_ids or []
    else:
        body = (
            f"Сегодня {format_date_ru()}, сезон — {current_season()}. "
            "Загляни, когда будет тихое утро — соберу заметки 🤍"
        )
        highlights = []
        idea_ids = []
        if top:
            best = top[0]
            snippet = (best.theme or (best.text or "")[:60] or "пост")
            highlights.append(
                {
                    "text": (
                        f"Недавно хорошо зашёл материал про «{snippet}» "
                        f"(вовлечённость {best.engagement:.0f})."
                    )
                }
            )

    ideas: list[IdeaCard] = []
    if idea_ids:
        result = await session.execute(select(Idea).where(Idea.id.in_(idea_ids)))
        for idea in result.scalars():
            ideas.append(
                IdeaCard(
                    theme=idea.theme,
                    format=idea.format,
                    description=idea.description,
                    personal_angle=idea.personal_angle,
                    visual=idea.visual,
                    effort=idea.effort if idea.effort in ("light", "medium", "deep") else "medium",
                    why_now=idea.why_now,
                    why=WhyBlock(summary=idea.why_now or "Из утреннего дайджеста"),
                    id=idea.id,
                    suggestion_id=idea.suggestion_id,
                )
            )
    elif await memory.count_posts() > 0:
        try:
            batch = await generate_ideas(session, count=2)
            ideas = batch.ideas
        except ModelAsleepError:
            pass

    reminders = []
    for item in plan[:5]:
        label = "черновик" if item.status == "written" else "задумано"
        reminders.append(f"{item.title} — {label}")

    return TodayResponse(
        digest=body,
        highlights=highlights,
        ideas=ideas,
        plan_reminders=reminders,
        activity=[
            ActivityItem(
                id=a.id,
                action=a.action,
                summary=a.summary,
                extra=a.extra or {},
                created_at=a.created_at.isoformat() if a.created_at else "",
            )
            for a in activity
        ],
        why=WhyBlock(
            summary="Собрала то, что заметила с прошлого визита",
            seasonality=f"{format_date_ru()}, {current_season()}",
        ),
    )

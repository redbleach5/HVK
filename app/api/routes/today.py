"""Вкладка «Сегодня» — утреннее резюме."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import related_post_labels
from app.agents.ideas import idea_row_to_card
from app.context.engine import current_season, format_date_ru
from app.db.models import Idea
from app.db.session import get_session
from app.memory.citations import digest_cites_posts, digest_from_posts
from app.memory.store import MemoryStore
from app.schemas.agents import IdeaCard
from app.schemas.api import TodayResponse
from app.schemas.common import ActivityItem, WhyBlock

router = APIRouter(tags=["today"])


@router.get("/today", response_model=TodayResponse)
async def today(session: AsyncSession = Depends(get_session)) -> TodayResponse:
    """Тихое резюме: дайджест, идеи, напоминания плана, история."""
    memory = MemoryStore(session)
    if await memory.count_posts() == 0:
        return TodayResponse(
            digest=(
                "Я ещё не читала твои тексты — без них это будет угадайка. "
                "Вставь несколько своих постов — и сводка станет настоящей 🤍"
            ),
            highlights=[],
            ideas=[],
            plan_reminders=[],
            activity=[],
            why=WhyBlock(
                summary="Архив пуст — не выдумываю блог",
                seasonality=f"{format_date_ru()}, {current_season()}",
            ),
        )

    digest_row = await memory.latest_digest()
    plan = await memory.open_plan_items()
    activity = await memory.recent_activity(8)
    recent = await memory.recent_posts(4)
    citations = await related_post_labels(session, limit=4)
    archive_body, archive_highlights = digest_from_posts(recent)

    if digest_row and digest_cites_posts(digest_row.body, recent):
        body = digest_row.body
        highlights = digest_row.highlights or archive_highlights
        idea_ids = digest_row.idea_ids or []
    elif archive_body:
        body = archive_body
        highlights = archive_highlights
        idea_ids = (digest_row.idea_ids if digest_row else None) or []
        if digest_row and digest_row.body and digest_row.body not in body:
            highlights = list(highlights) + [{"text": digest_row.body}]
    else:
        body = (
            f"Сегодня {format_date_ru()}, сезон — {current_season()}. "
            "Загляни, когда будет тихое утро — соберу заметки 🤍"
        )
        highlights = []
        idea_ids = []

    ideas: list[IdeaCard] = []
    if idea_ids:
        result = await session.execute(select(Idea).where(Idea.id.in_(idea_ids)))
        ideas = [idea_row_to_card(idea) for idea in result.scalars()]
    if not ideas:
        stored = await memory.recent_ideas(3, statuses=("new",))
        if not stored:
            stored = await memory.recent_ideas(3)
        ideas = [idea_row_to_card(idea) for idea in stored]

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
            summary="Собрала из твоих текстов и того, что заметила",
            related_posts=citations,
            seasonality=f"{format_date_ru()}, {current_season()}",
        ),
    )

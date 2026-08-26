"""Аналитик аудитории: портрет, что работает, вопросы, рекомендации."""

from __future__ import annotations

import json
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
from app.llm.client import get_llm
from app.memory.store import MemoryStore
from app.schemas.agents import AudienceInsight, AudienceReport
from app.schemas.common import WhyBlock

logger = logging.getLogger(__name__)


class _AudienceLlmOut(BaseModel):
    """Сырой отчёт аудитории."""

    portrait: str
    what_works: list[str] = Field(default_factory=list)
    frequent_questions: list[str] = Field(default_factory=list)
    unmet_needs: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    insights: list[AudienceInsight] = Field(default_factory=list)
    why: WhyBlock


async def analyze_audience(session: AsyncSession) -> AudienceReport:
    """Строит портрет аудитории по постам, статистике и комментариям."""
    memory = MemoryStore(session)
    if await memory.count_posts() == 0:
        return AudienceReport(
            portrait="Пока нет архива — портрет аудитории появится, когда будут её посты.",
            what_works=[],
            frequent_questions=[],
            unmet_needs=[],
            recommendations=[],
            insights=[],
            why=WhyBlock(summary="Архив пуст — не выдумываю читателей"),
        )
    context = await build_agent_context(session)
    posts = await memory.recent_posts(25)
    top = await memory.top_posts(60, 8)
    labels = await related_post_labels(session, limit=5)

    def _pack(post) -> dict:
        return {
            "date": post.published_at.isoformat() if post.published_at else None,
            "theme": post.theme,
            "engagement": post.engagement,
            "likes": post.likes,
            "comments_count": post.comments_count,
            "views": post.views,
            "text": (post.text or "")[:500],
            "comments": (post.comments or [])[:8],
        }

    data_blob = {
        "recent": [_pack(p) for p in posts],
        "top": [_pack(p) for p in top],
        "posts_count": await memory.count_posts(),
    }

    system = (
        f"{SYSTEM_ASSISTANT}\n"
        "Ты аналитик аудитории лайфстайл-блога. Опирайся только на данные. "
        "Каждый инсайт — с based_on и why. Не выдумывай цифры."
    )
    user = f"""{context}

Данные постов и комментариев:
{json.dumps(data_blob, ensure_ascii=False)}

Верни JSON: portrait, what_works, frequent_questions, unmet_needs,
recommendations, insights (title, body, based_on, why), why.
"""

    parsed = await get_llm().complete_json(
        system=system,
        user=user,
        schema=_AudienceLlmOut,
        temperature=0.3,
        max_tokens=3500,
    )
    why = ensure_why(parsed.why, "Собрала картину по статистике и комментариям архива")
    why.related_posts = labels

    suggestion = await save_agent_suggestion(
        session,
        kind="audience",
        title="Портрет аудитории",
        payload={"portrait": parsed.portrait},
        why=why,
        log_action="analytics",
        log_summary="Обновила взгляд на аудиторию",
    )
    await session.commit()

    report = AudienceReport(
        portrait=parsed.portrait,
        what_works=parsed.what_works,
        frequent_questions=parsed.frequent_questions,
        unmet_needs=parsed.unmet_needs,
        recommendations=parsed.recommendations,
        insights=parsed.insights,
        why=why,
        suggestion_id=suggestion.id,
    )
    logger.info("Аналитика аудитории suggestion=%s", suggestion.id)
    return report

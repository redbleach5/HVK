"""Аналитик аудитории: портрет, что работает, вопросы, рекомендации."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import (
    SYSTEM_JSON,
    ensure_why,
    pack_for_agent,
    save_agent_suggestion,
)
from app.db.models import AudienceCache
from app.llm.client import get_llm
from app.memory.store import MemoryStore
from app.schemas.agents import AudienceInsight, AudienceReport
from app.schemas.common import WhyBlock, WhyBlockLlm

logger = logging.getLogger(__name__)


class _AudienceInsightLlm(BaseModel):
    title: str = ""
    body: str = ""
    based_on: str = ""
    why: WhyBlockLlm = Field(default_factory=WhyBlockLlm)

    @field_validator("why", mode="before")
    @classmethod
    def _why(cls, value: object) -> object:
        if isinstance(value, str):
            return {"summary": value.strip()}
        return value or {}


class _AudienceLlmOut(BaseModel):
    """Сырой отчёт аудитории."""

    portrait: str
    what_works: list[str] = Field(default_factory=list)
    frequent_questions: list[str] = Field(default_factory=list)
    unmet_needs: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    insights: list[_AudienceInsightLlm] = Field(default_factory=list)
    why: WhyBlockLlm = Field(default_factory=WhyBlockLlm)

    @field_validator("why", mode="before")
    @classmethod
    def _why(cls, value: object) -> object:
        if isinstance(value, str):
            return {"summary": value.strip()}
        return value or {}


async def analyze_audience(session: AsyncSession) -> AudienceReport:
    """Строит портрет аудитории по постам, статистике и комментариям.

    Кэшируется по подписи архива. Invalidate — в `save_pasted_posts` / `reindex_posts`.
    Повторный запрос на тот же архив — мгновенный, без LLM.
    """
    memory = MemoryStore(session)
    posts_count = await memory.count_author_posts()
    if posts_count == 0:
        return AudienceReport(
            portrait="Пока нет архива — портрет аудитории появится, когда будут её посты.",
            what_works=[],
            frequent_questions=[],
            unmet_needs=[],
            recommendations=[],
            insights=[],
            why=WhyBlock(summary="Архив пуст — не выдумываю читателей"),
        )

    signature = await memory.posts_signature()
    cached = await memory.get_audience_cache(signature)
    if cached is not None:
        logger.info("Аудит-отчёт из кэша signature=%s", signature)
        return _report_from_cache(cached)

    context, labels = await pack_for_agent(session, with_session=False)
    posts = await memory.recent_posts(12)
    top = await memory.top_posts(60, 5)

    def _pack(post) -> dict:
        return {
            "date": post.published_at.isoformat() if post.published_at else None,
            "theme": post.theme,
            "engagement": post.engagement,
            "likes": post.likes,
            "comments_count": post.comments_count,
            "text": (post.text or "")[:220],
            "comments": (post.comments or [])[:3],
        }

    data_blob = {
        "recent": [_pack(p) for p in posts],
        "top": [_pack(p) for p in top],
        "posts_count": posts_count,
    }

    system = (
        f"{SYSTEM_JSON}\n"
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
        max_tokens=2200,
        label="audience",
    )
    why = ensure_why(parsed.why.model_dump(), "Собрала картину по статистике и комментариям архива")
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
    insights = [
        AudienceInsight(
            title=i.title,
            body=i.body,
            based_on=i.based_on,
            why=ensure_why(i.why.model_dump(), i.body[:120] or i.title),
        )
        for i in parsed.insights
    ]
    report = AudienceReport(
        portrait=parsed.portrait,
        what_works=parsed.what_works,
        frequent_questions=parsed.frequent_questions,
        unmet_needs=parsed.unmet_needs,
        recommendations=parsed.recommendations,
        insights=insights,
        why=why,
        suggestion_id=suggestion.id,
    )
    await memory.save_audience_cache(
        signature,
        report.model_dump(),
        suggestion_id=suggestion.id,
        posts_count=posts_count,
    )
    await session.commit()
    logger.info("Аналитика аудитории suggestion=%s signature=%s", suggestion.id, signature)
    return report


def _report_from_cache(cached: AudienceCache) -> AudienceReport:
    """Восстанавливает отчёт из кэша. why пересобирается, чтобы быть свежим по сезонности."""
    data = dict(cached.report or {})
    # why может быть dict из JSON — нормализуем
    raw_why = data.get("why") or {}
    if isinstance(raw_why, dict):
        why = WhyBlock.model_validate(raw_why)
    elif isinstance(raw_why, WhyBlock):
        why = raw_why
    else:
        why = WhyBlock(summary="Собрала картину по статистике и комментариям архива")
    return AudienceReport(
        portrait=data.get("portrait") or "",
        what_works=data.get("what_works") or [],
        frequent_questions=data.get("frequent_questions") or [],
        unmet_needs=data.get("unmet_needs") or [],
        recommendations=data.get("recommendations") or [],
        insights=[
            AudienceInsight.model_validate(i) if isinstance(i, dict) else i
            for i in (data.get("insights") or [])
        ],
        why=why,
        suggestion_id=cached.suggestion_id,
    )

"""Схемы ответов агентов. У каждой есть обязательный блок why."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.common import WhyBlock


class PhotoScores(BaseModel):
    """Оценки кадра по шкале 1–10."""

    atmosphere: int = Field(..., ge=1, le=10)
    composition: int = Field(..., ge=1, le=10)
    light: int = Field(..., ge=1, le=10)
    palette: int = Field(..., ge=1, le=10)
    storytelling: int = Field(..., ge=1, le=10)
    aesthetic_fit: int = Field(..., ge=1, le=10)


class PhotoAdvice(BaseModel):
    """Один совет по фото, по которому автор может дать обратную связь."""

    text: str
    suggestion_id: Optional[int] = None


class PhotoAnalysis(BaseModel):
    """Вердикт фото-аналитика."""

    verdict: str
    scores: PhotoScores
    advice: list[str]
    caption_direction: str
    why: WhyBlock
    best_in_series: Optional[int] = Field(
        default=None, description="Индекс лучшего кадра в серии, с нуля"
    )
    series_comparison: Optional[str] = None
    suggestion_id: Optional[int] = None
    advice_suggestions: list[PhotoAdvice] = Field(default_factory=list)


class TextEdit(BaseModel):
    """Одна правка черновика."""

    original: str
    revised: str
    explanation: str
    suggestion_id: Optional[int] = None
    accepted: Optional[bool] = None


class EditorResult(BaseModel):
    """Результат редактора текста."""

    revised_text: str
    edits: list[TextEdit]
    alternative_openings: list[str]
    in_voice: bool
    voice_notes: str
    why: WhyBlock
    suggestion_id: Optional[int] = None


class AudienceInsight(BaseModel):
    """Один инсайт об аудитории с опорой на данные."""

    title: str
    body: str
    based_on: str
    why: WhyBlock


class AudienceReport(BaseModel):
    """Портрет аудитории и рекомендации."""

    portrait: str
    what_works: list[str]
    frequent_questions: list[str]
    unmet_needs: list[str]
    recommendations: list[str]
    insights: list[AudienceInsight]
    why: WhyBlock
    suggestion_id: Optional[int] = None


class IdeaCard(BaseModel):
    """Карточка идеи контента."""

    theme: str
    format: str
    description: str
    personal_angle: str
    visual: str
    effort: Literal["light", "medium", "deep"] = "medium"
    why_now: str
    why: WhyBlock
    id: Optional[int] = None
    suggestion_id: Optional[int] = None


class IdeaBatch(BaseModel):
    """Пачка идей от генератора."""

    ideas: list[IdeaCard]


class ConciergeReply(BaseModel):
    """Черновик ответа на личное сообщение. Бот сам ничего не отправляет."""

    category: Literal["ad", "product_question", "compliment", "other"]
    category_label: str
    related_post: Optional[str] = None
    draft_reply: str
    why: WhyBlock
    suggestion_id: Optional[int] = None


class ArchiveHit(BaseModel):
    """Похожий или сезонный пост из архива."""

    post_id: int
    text_preview: str
    published_at: Optional[str] = None
    theme: Optional[str] = None
    engagement: float = 0.0
    why_relevant: str


class ArchiveSearchResult(BaseModel):
    """Результат поиска по архиву."""

    hits: list[ArchiveHit]
    why: WhyBlock

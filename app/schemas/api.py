"""Схемы HTTP API для онбординга, плана, сегодняшнего дня."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.schemas.agents import AudienceReport, IdeaCard
from app.schemas.common import ActivityItem, WhyBlock


class OnboardingProfileIn(BaseModel):
    """Шаг 1 онбординга: название блога и пара слов о себе."""

    blog_name: str = Field(..., min_length=1, max_length=200)
    about: str = Field(default="", max_length=2000)


class OnboardingStatus(BaseModel):
    """Состояние знакомства с автором."""

    step: int
    done: bool
    blog_name: str
    about: str
    posts_imported: int
    voice_ready: bool


class TodayResponse(BaseModel):
    """Сердце дашборда — тихое утреннее резюме."""

    digest: str
    highlights: list[dict[str, Any]] = Field(default_factory=list)
    ideas: list[IdeaCard] = Field(default_factory=list)
    plan_reminders: list[str] = Field(default_factory=list)
    activity: list[ActivityItem] = Field(default_factory=list)
    why: Optional[WhyBlock] = None


class TextEditIn(BaseModel):
    """Черновик на редактуру."""

    draft: str = Field(..., min_length=1)
    topic_hint: str = ""
    plan_item_id: Optional[int] = None


class ApplyEditIn(BaseModel):
    """Принятие или отклонение одной правки."""

    suggestion_id: int
    accepted: bool
    current_text: str


class IdeaGenerateIn(BaseModel):
    """Запрос на пачку идей."""

    count: int = Field(default=3, ge=1, le=6)


class PlanItemOut(BaseModel):
    """Пункт плана для интерфейса."""

    id: int
    idea_id: Optional[int] = None
    title: str
    draft_text: str
    status: Literal["conceived", "written", "published"]
    scheduled_date: Optional[str] = None
    published_post_id: Optional[int] = None


class PlanItemUpdate(BaseModel):
    """Смена статуса или даты пункта плана."""

    status: Optional[Literal["conceived", "written", "published"]] = None
    scheduled_date: Optional[str] = None
    draft_text: Optional[str] = None


class PublishIn(BaseModel):
    """Отложенный постинг только с явным подтверждением."""

    confirm: bool = False
    message: str = ""
    publish_date_unix: Optional[int] = None
    plan_item_id: Optional[int] = None
    photo_paths: list[str] = Field(default_factory=list)


class PublishOut(BaseModel):
    """Результат публикации в VK."""

    ok: bool = True
    vk_post_id: str = ""
    post_id: Optional[int] = None
    plan_item_id: Optional[int] = None
    photos_attached: int = 0
    photos_warning: Optional[str] = None


class ConciergeIn(BaseModel):
    """Входящее ЛС для черновика ответа."""

    message_text: str = Field(..., min_length=1)


class InboxItem(BaseModel):
    """Короткое превью входящего диалога ЛС."""

    peer_id: int
    preview: str
    date: Optional[str] = None
    unread: int = 0


class InboxOut(BaseModel):
    """Список входящих ЛС или мягкий отказ по правам."""

    items: list[InboxItem] = Field(default_factory=list)
    available: bool = True
    message: str = ""


class RhythmHintOut(BaseModel):
    """Подсказка по ритму публикаций."""

    hint: str


class PlanFromTextIn(BaseModel):
    """Создать пункт плана из текста архива или заготовки."""

    title: str = Field(..., min_length=1, max_length=240)
    draft_text: str = ""


class ChatHistoryItem(BaseModel):
    """Одно сообщение в истории чата."""

    id: int
    role: Literal["user", "assistant"]
    content: str
    cards: list[dict[str, Any]] = Field(default_factory=list)
    suggestion_ids: list[int] = Field(default_factory=list)
    created_at: str = ""


class ChatCard(BaseModel):
    """Структурированный блок в ответе чата (идея, правка, ЛС…)."""

    type: str
    title: str = ""
    body: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    suggestion_id: Optional[int] = None


class ChatOut(BaseModel):
    """Ответ чата."""

    reply: str
    cards: list[ChatCard] = Field(default_factory=list)
    suggestion_ids: list[int] = Field(default_factory=list)
    intent: str = "general"


class ChatHistoryOut(BaseModel):
    """История чата."""

    messages: list[ChatHistoryItem] = Field(default_factory=list)


class VoiceProfileOut(BaseModel):
    """Текущий профиль голоса."""

    version: int
    profile: dict[str, Any]
    created_at: str


class AnalyticsOut(BaseModel):
    """Данные вкладки аналитики."""

    series: list[dict[str, Any]]
    top_posts: list[dict[str, Any]]
    report: Optional[AudienceReport] = None
    posts_count: int = 0

"""Общие схемы: объяснимость и обратная связь."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class WhyBlock(BaseModel):
    """Блок «почему я это предлагаю». Обязателен у каждого предложения агента."""

    summary: str = Field(..., description="Коротко, человеческим языком")
    related_posts: list[str] = Field(default_factory=list, description="Заголовки или даты прошлых постов")
    seasonality: Optional[str] = None
    audience_pattern: Optional[str] = None


class SuggestionFeedback(BaseModel):
    """Реакция автора на предложение."""

    accepted: bool
    note: str = ""


class HealthStatus(BaseModel):
    """Состояние сервисов."""

    ok: bool
    brain: bool
    eyes: bool
    vk_configured: bool
    telegram_configured: bool
    message: str


class ActivityItem(BaseModel):
    """Запись истории действий."""

    id: int
    action: str
    summary: str
    extra: dict[str, Any] = Field(default_factory=dict)
    created_at: str

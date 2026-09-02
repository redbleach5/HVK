"""Общие схемы: объяснимость и обратная связь."""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class WhyBlock(BaseModel):
    """Блок «почему я это предлагаю». Обязателен у каждого предложения агента."""

    summary: str = Field(..., description="Коротко, человеческим языком")
    related_posts: list[str] = Field(
        default_factory=list, description="Заголовки или даты прошлых постов"
    )
    seasonality: Optional[str] = None
    audience_pattern: Optional[str] = None

    @field_validator("related_posts", mode="before")
    @classmethod
    def _split_related(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [part.strip() for part in re.split(r"[,;\n]", value) if part.strip()]
        return value


class WhyBlockLlm(BaseModel):
    """Мягкая схема why для JSON модели — без жёстких полей."""

    summary: str = ""
    related_posts: list[str] = Field(default_factory=list)
    seasonality: Optional[str] = None
    audience_pattern: Optional[str] = None

    @field_validator("related_posts", mode="before")
    @classmethod
    def _split_related(cls, value: Any) -> list[str]:
        return WhyBlock._split_related(value)

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, value: Any) -> str:
        return (value or "").strip() if isinstance(value, str) else str(value or "")

    @classmethod
    def coerce(cls, value: Any) -> "WhyBlockLlm":
        if isinstance(value, str):
            return cls(summary=value.strip())
        if isinstance(value, dict):
            return cls.model_validate(value)
        return cls()


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


class DiagnosticsOut(BaseModel):
    """Самодиагностика для скриптов и мягкой подсказки в UI."""

    ok: bool
    checked_at: str
    author_hint: Optional[str] = None
    issues: list[str] = Field(default_factory=list)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    chat_latency: dict[str, Any] = Field(default_factory=dict)
    json_latency: dict[str, Any] = Field(default_factory=dict)
    recent_calls: list[dict[str, Any]] = Field(default_factory=list)
    ops_insight: Optional[str] = None


class ActivityItem(BaseModel):
    """Запись истории действий."""

    id: int
    action: str
    summary: str
    extra: dict[str, Any] = Field(default_factory=dict)
    created_at: str

"""Общие схемы: объяснимость и обратная связь."""

from __future__ import annotations

import re
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


def as_str_list(value: Any) -> list[str]:
    """Список строк из того, что реально присылает модель.

    Мозг (qwen3.6) отвечает словарём там, где в схеме строка
    (`{"action": "Поделиться…"}`) или одной строкой вместо списка.
    Такой ответ — не повод ронять агента: приводим к списку строк.
    """
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, dict):
        parts = [part for item in value.values() for part in as_str_list(item)]
        return [" — ".join(parts)] if parts else []
    if isinstance(value, (list, tuple, set)):
        return [part for item in value for part in as_str_list(item)]
    text = str(value).strip()
    return [text] if text else []


def as_obj_list(value: Any) -> list[Any]:
    """Список объектов: модель отдаёт объект, словарь с нумерацией или список.

    Словарь с вложенными объектами («1»: {...}) — это коллекция; словарь
    из простых полей (одна идея целиком) — один объект.
    """
    if isinstance(value, dict):
        if value and all(isinstance(item, dict) for item in value.values()):
            return list(value.values())
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value] if value else []


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
        """Строка, id поста числом или объект — всё становится списком строк."""
        if isinstance(value, str):
            return [part.strip() for part in re.split(r"[,;\n]", value) if part.strip()]
        return as_str_list(value)


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

    @model_validator(mode="before")
    @classmethod
    def _soft(cls, value: Any) -> Any:
        """Модель может прислать why строкой или пустотой вместо объекта."""
        if value is None:
            return {}
        if isinstance(value, str):
            return {"summary": value.strip()}
        return value


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

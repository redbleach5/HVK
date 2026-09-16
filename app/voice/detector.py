"""Детектор: звучит ли черновик как автор."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import get_llm
from app.memory.store import MemoryStore
from app.schemas.common import as_str_list


class VoiceCheck(BaseModel):
    """Результат проверки «в голосе ли текст»."""

    in_voice: bool
    what_stands_out: str
    details: list[str] = Field(default_factory=list)

    @field_validator("details", mode="before")
    @classmethod
    def _details(cls, value: object) -> list[str]:
        return as_str_list(value)


async def detect_voice(session: AsyncSession, text: str, topic_hint: str = "") -> VoiceCheck:
    """Сравнивает черновик с живым профилем голоса и объясняет расхождения."""
    memory = MemoryStore(session)
    voice = await memory.latest_voice()
    profile = voice.profile if voice else {}
    if not text.strip():
        return VoiceCheck(
            in_voice=True,
            what_stands_out="текста пока нет — нечего сверять",
            details=[],
        )

    system = (
        "Ты бережный редактор голоса. Не переписывай текст. "
        "Скажи, звучит ли он как автор, и ЧТО именно выбивается, если выбивается. "
        "Не ругай за искренность, ругай за чужой тон: рекламный, экспертный, кричащий."
    )
    user = f"""Профиль голоса:
{profile}

Тема (если есть): {topic_hint or "не указана"}

Черновик:
{text}

Верни JSON: in_voice (bool), what_stands_out (строка), details (список коротких замечаний).
"""
    return await get_llm().complete_json(system=system, user=user, schema=VoiceCheck)

"""Фото-аналитик: атмосфера, композиция, свет, палитра, сторителлинг."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import (
    SYSTEM_ASSISTANT,
    ensure_why,
    pack_for_agent,
    save_agent_suggestion,
)
from app.llm.client import get_llm
from app.llm.exceptions import EmptyArchiveError
from app.memory.store import MemoryStore
from app.schemas.agents import PhotoAdvice, PhotoAnalysis, PhotoScores
from app.schemas.common import WhyBlock

logger = logging.getLogger(__name__)


class _PhotoLlmOut(BaseModel):
    """Сырой ответ vision-модели до привязки suggestion_id."""

    verdict: str
    scores: PhotoScores
    advice: list[str] = Field(default_factory=list)
    caption_direction: str = ""
    why: WhyBlock
    best_in_series: int | None = None
    series_comparison: str | None = None

    @field_validator("best_in_series", mode="before")
    @classmethod
    def _series_index(cls, value: object) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
        return None

    @field_validator("advice", mode="before")
    @classmethod
    def _advice_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            parts = [p.strip(" •—-") for p in value.replace(". ", ".\n").split("\n") if p.strip()]
            return [p.rstrip(".") + "." if p and not p.endswith(".") else p for p in parts][:5]
        return value  # type: ignore[return-value]


def _image_to_data_url(path: Path) -> str:
    """Читает файл и кодирует в data-url для vision API."""
    raw = path.read_bytes()
    suffix = path.suffix.lower().lstrip(".")
    mime = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
    }.get(suffix, "image/jpeg")
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


async def analyze_photos(
    session: AsyncSession,
    image_paths: list[Path],
) -> PhotoAnalysis:
    """Оценивает одно или несколько фото как арт-директор lifestyle-журнала."""
    if not image_paths:
        raise ValueError("нужно хотя бы одно фото")
    if await MemoryStore(session).count_author_posts() == 0:
        raise EmptyArchiveError("no posts")

    context, labels = await pack_for_agent(session, with_session=False)
    series_note = (
        f"Это серия из {len(image_paths)} кадров. "
        "Сравни их, укажи best_in_series (индекс с нуля) и series_comparison."
        if len(image_paths) > 1
        else "Одно фото. best_in_series и series_comparison можно не заполнять."
    )

    system = (
        f"{SYSTEM_ASSISTANT}\n"
        "Ты смотришь кадр как подруга с вкусом, не как нейросеть и не как техредактор. "
        "Пиши по-русски, коротко, тепло. Без английских терминов, без grain/JSON/промптов. "
        "Вердикт — 1–2 предложения про ощущение кадра. Советы — что поправить в съёмке, по-человечески."
    )
    archive_line = ", ".join(labels) if labels else "архива ещё нет — не выдумывай чужие посты"
    user = f"""{context}

{series_note}

Ориентир по её архиву: {archive_line}.

JSON-поля:
verdict — строка;
scores — объект atmosphere, composition, light, palette, storytelling, aesthetic_fit (целые 1–10);
advice — массив из 2–4 коротких русских строк;
caption_direction — строка, куда может пойти подпись, не готовый пост;
why — summary (строка), related_posts (массив коротких меток из архива или пустой), seasonality, audience_pattern;
best_in_series — число или null;
series_comparison — строка или null.
"""

    images = [_image_to_data_url(p) for p in image_paths]
    parsed = await get_llm().complete_json(
        system=system,
        user=user,
        schema=_PhotoLlmOut,
        images=images,
        temperature=0.45,
        max_tokens=2000,
        no_reasoning=True,
        label="photo",
    )

    why = ensure_why(parsed.why, "Опираюсь на эстетику блога и то, что уже заходило")
    why.related_posts = labels

    parent = await save_agent_suggestion(
        session,
        kind="photo",
        title=parsed.verdict[:200] or "Разбор фото",
        payload={
            "verdict": parsed.verdict,
            "scores": parsed.scores.model_dump(),
            "advice": parsed.advice,
            "caption_direction": parsed.caption_direction,
            "paths": [str(p) for p in image_paths],
        },
        why=why,
        log_action="photo",
        log_summary=f"Разобрала {len(image_paths)} фото",
    )

    advice_suggestions: list[PhotoAdvice] = []
    for tip in parsed.advice:
        child = await save_agent_suggestion(
            session,
            kind="photo_advice",
            title=tip[:200],
            payload={"text": tip},
            why=why,
            parent_id=parent.id,
        )
        advice_suggestions.append(PhotoAdvice(text=tip, suggestion_id=child.id))

    await session.commit()

    result = PhotoAnalysis(
        verdict=parsed.verdict,
        scores=parsed.scores,
        advice=parsed.advice,
        caption_direction=parsed.caption_direction,
        why=why,
        best_in_series=parsed.best_in_series,
        series_comparison=parsed.series_comparison,
        suggestion_id=parent.id,
        advice_suggestions=advice_suggestions,
    )
    logger.info("Фото-анализ suggestion=%s", parent.id)
    return result

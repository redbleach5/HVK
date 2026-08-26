"""Тихие фоновые задачи: статистика VK, голос, утренний дайджест."""

from __future__ import annotations

import logging
from typing import Any, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel, Field

from app.agents.ideas import generate_ideas
from app.context.engine import ContextEngine, current_season, format_date_ru
from app.db.models import Digest
from app.db.session import SessionLocal
from app.llm.client import get_llm
from app.llm.exceptions import EmptyArchiveError, ModelAsleepError
from app.memory.store import MemoryStore
from app.vk.client import is_configured, refresh_stats
from app.voice.profile import build_voice_profile

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


class _DigestLlm(BaseModel):
    body: str
    highlights: list[dict[str, Any]] = Field(default_factory=list)


async def job_refresh_vk_stats() -> None:
    """Обновляет статистику постов, если VK настроен."""
    if not is_configured():
        logger.debug("VK не настроен — пропускаю refresh stats")
        return
    try:
        async with SessionLocal() as session:
            n = await refresh_stats(session)
            logger.info("Планировщик: обновлена статистика VK (%s)", n)
    except Exception:
        logger.exception("Планировщик: ошибка refresh VK stats")


async def job_update_voice() -> None:
    """Тихо обновляет профиль голоса по архиву."""
    try:
        async with SessionLocal() as session:
            count = await MemoryStore(session).count_posts()
            if count < 3:
                logger.debug("Мало постов для обновления голоса")
                return
            await build_voice_profile(session, source="scheduler")
            logger.info("Планировщик: профиль голоса обновлён")
    except EmptyArchiveError:
        logger.info("Планировщик: нет архива — голос не выдумываю")
    except ModelAsleepError:
        logger.info("Планировщик: модель спит — голос позже")
    except Exception:
        logger.exception("Планировщик: ошибка обновления голоса")


async def job_prepare_morning_digest() -> None:
    """Готовит утреннее резюме в БД. Не пушит автору."""
    try:
        async with SessionLocal() as session:
            context = await ContextEngine(session).build()
            memory = MemoryStore(session)
            top = await memory.top_posts(21, 3)
            plan = await memory.open_plan_items()

            system = (
                "Ты готовишь тихое утреннее резюме для автора блога. "
                "Без тревоги и без пуша. 2–4 предложения + highlights. "
                "Не выдумывай факты."
            )
            top_lines = "\n".join(
                f"- {(p.theme or '')}: eng={p.engagement:.0f}, {(p.text or '')[:100]}"
                for p in top
            ) or "- данных мало"
            plan_lines = "\n".join(f"- {i.title} [{i.status}]" for i in plan[:5]) or "- план пуст"

            user = f"""{context}

Топ недавних:
{top_lines}

План:
{plan_lines}

Сегодня {format_date_ru()}, сезон {current_season()}.
Верни JSON: body (строка резюме), highlights (список объектов с ключом text).
"""
            try:
                parsed = await get_llm().complete_json(
                    system=system,
                    user=user,
                    schema=_DigestLlm,
                    temperature=0.4,
                    max_tokens=1200,
                )
                body = parsed.body
                highlights = parsed.highlights
            except ModelAsleepError:
                body = (
                    f"Сегодня {format_date_ru()}, {current_season()}. "
                    "Модель ещё отдыхает — загляни позже за свежими идеями 🤍"
                )
                highlights = [{"text": "Когда модель проснётся, соберу заметки по статистике"}]

            idea_ids: list[int] = []
            try:
                batch = await generate_ideas(session, count=2)
                idea_ids = [c.id for c in batch.ideas if c.id]
            except ModelAsleepError:
                logger.info("Планировщик: идеи для дайджеста пропущены — модель спит")
            except Exception:
                logger.exception("Планировщик: не удалось сгенерировать идеи для дайджеста")

            digest = Digest(body=body, highlights=highlights, idea_ids=idea_ids)
            session.add(digest)
            await memory.log("digest", "Подготовила утреннее резюме")
            await session.commit()
            logger.info("Планировщик: дайджест сохранён id=%s", digest.id)
    except Exception:
        logger.exception("Планировщик: ошибка morning digest")


def start_scheduler() -> AsyncIOScheduler:
    """Запускает фоновые задачи. Идемпотентно."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(
        job_refresh_vk_stats,
        "interval",
        hours=6,
        id="vk_stats",
        replace_existing=True,
    )
    scheduler.add_job(
        job_update_voice,
        "cron",
        hour=3,
        minute=15,
        id="voice_update",
        replace_existing=True,
    )
    scheduler.add_job(
        job_prepare_morning_digest,
        "cron",
        hour=7,
        minute=30,
        id="morning_digest",
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("Планировщик запущен")
    return scheduler


def stop_scheduler() -> None:
    """Останавливает планировщик при shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Планировщик остановлен")
    _scheduler = None


def get_scheduler() -> Optional[AsyncIOScheduler]:
    """Текущий экземпляр планировщика или None."""
    return _scheduler

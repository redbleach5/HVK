"""Задачи улучшения в простое — по одной, без конкуренции с автором."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.audience import analyze_audience
from app.agents.ideas import generate_ideas
from app.db.models import Post
from app.diagnostics.engine import run_diagnostics
from app.llm.client import get_llm
from app.llm.exceptions import EmptyArchiveError, ModelAsleepError
from app.memory.chroma import get_chroma
from app.memory.ingest import reindex_posts
from app.memory.store import MemoryStore
from app.memory.themes import infer_theme
from app.voice.profile import build_voice_profile

logger = logging.getLogger(__name__)

IdleTask = Callable[[AsyncSession], Awaitable[bool]]


async def task_sync_themes(session: AsyncSession) -> bool:
    """Темы постов без LLM — для аналитики и подсказок."""
    result = await session.execute(select(Post).where(Post.text != ""))
    changed = 0
    for post in result.scalars():
        if (post.theme or "").strip():
            continue
        text = (post.text or "").strip()
        if not text:
            continue
        post.theme = infer_theme(text)
        changed += 1
    if changed:
        await session.commit()
        logger.info("Idle: темы для %s постов", changed)
    return changed > 0


async def task_refresh_rhythm(session: AsyncSession) -> bool:
    memory = MemoryStore(session)
    await memory.refresh_rhythm()
    await session.commit()
    logger.info("Idle: ритм публикаций обновлён")
    return True


async def task_reindex_archive(session: AsyncSession) -> bool:
    memory = MemoryStore(session)
    author_n = await memory.count_author_posts()
    if author_n == 0:
        return False
    try:
        indexed = get_chroma().count()
    except Exception:
        indexed = 0
    if indexed >= author_n:
        return False
    n = await reindex_posts(session)
    await session.commit()
    logger.info("Idle: переиндекс %s постов (было %s/%s)", n, indexed, author_n)
    return n > 0


async def task_voice_if_stale(session: AsyncSession) -> bool:
    memory = MemoryStore(session)
    if await memory.count_author_posts() < 3:
        return False
    signature = await memory.posts_signature()
    voice = await memory.latest_voice()
    if voice:
        prof = voice.profile or {}
        if prof.get("archive_signature") == signature:
            age = datetime.utcnow() - (voice.created_at or datetime.utcnow())
            if age < timedelta(days=7):
                return False
    await build_voice_profile(session, source="idle")
    logger.info("Idle: голос обновлён")
    return True


async def task_warm_audience_cache(session: AsyncSession) -> bool:
    memory = MemoryStore(session)
    if await memory.count_author_posts() < 2:
        return False
    signature = await memory.posts_signature()
    if await memory.get_audience_cache(signature) is not None:
        return False
    await analyze_audience(session)
    logger.info("Idle: кэш аудитории signature=%s", signature)
    return True


async def task_warm_ideas(session: AsyncSession) -> bool:
    memory = MemoryStore(session)
    if await memory.count_author_posts() < 2:
        return False
    recent = await memory.recent_ideas(6)
    if len(recent) >= 3:
        newest = recent[0].created_at
        if newest and datetime.utcnow() - newest < timedelta(hours=36):
            return False
    await generate_ideas(session, count=2)
    logger.info("Idle: подогрела %s идей", 2)
    return True


async def task_light_diagnostics(session: AsyncSession) -> bool:
    await run_diagnostics(session, probe=False, insight=False)
    return True


# Приоритет: сначала без LLM, потом тяжёлые прогревы.
IDLE_TASKS: list[tuple[str, float, bool, IdleTask]] = [
    ("sync_themes", 3600, False, task_sync_themes),
    ("refresh_rhythm", 6 * 3600, False, task_refresh_rhythm),
    ("reindex_archive", 12 * 3600, False, task_reindex_archive),
    ("voice_stale", 24 * 3600, True, task_voice_if_stale),
    ("audience_cache", 8 * 3600, True, task_warm_audience_cache),
    ("ideas_warm", 6 * 3600, True, task_warm_ideas),
    ("diagnostics", 3 * 3600, False, task_light_diagnostics),
]

_last_run: dict[str, float] = {}


def pick_next_task(now: float) -> tuple[str, bool, IdleTask] | None:
    for name, interval, uses_llm, fn in IDLE_TASKS:
        prev = _last_run.get(name, 0.0)
        if now - prev >= interval:
            return name, uses_llm, fn
    return None


def mark_task_ran(name: str, now: float) -> None:
    _last_run[name] = now

"""Фоновый цикл: одна задача улучшения, когда автор не пишет."""

from __future__ import annotations

import asyncio
import logging
import time

from app.config import get_settings
from app.db.session import SessionLocal
from app.idle.gpu import vram_allows_llm
from app.idle.gpu import max_free_vram_mb
from app.idle.state import is_idle, mark_idle_task_done, snapshot
from app.idle.tasks import mark_task_ran, pick_next_task
from app.llm.client import get_llm
from app.llm.exceptions import EmptyArchiveError, ModelAsleepError

logger = logging.getLogger(__name__)

_worker_task: asyncio.Task | None = None
_stop = asyncio.Event()


async def idle_worker_loop() -> None:
    settings = get_settings()
    if not settings.idle_worker_enabled:
        logger.info("Idle worker выключен")
        return

    logger.info(
        "Idle worker: quiet=%ss, interval=%ss",
        settings.idle_quiet_seconds,
        settings.idle_poll_seconds,
    )
    while not _stop.is_set():
        try:
            await asyncio.wait_for(_stop.wait(), timeout=settings.idle_poll_seconds)
            break
        except asyncio.TimeoutError:
            pass

        if not await is_idle(quiet_seconds=settings.idle_quiet_seconds):
            continue

        picked = pick_next_task(time.monotonic())
        if picked is None:
            continue

        name, uses_llm, fn = picked
        if uses_llm:
            snap = await snapshot(quiet_seconds=settings.idle_quiet_seconds)
            if int(snap.get("active_llm") or 0) > 0:
                continue
            if not await is_idle(quiet_seconds=settings.idle_quiet_seconds):
                continue
            brain = await get_llm().ping_brain()
            if not brain:
                logger.debug("Idle: модель спит — %s позже", name)
                continue
            if not await vram_allows_llm(
                min_free_mb=settings.idle_min_vram_mb,
                brain_loaded=brain,
            ):
                logger.debug("Idle: мало VRAM — %s пропущена", name)
                continue

        try:
            async with SessionLocal() as session:
                done = await fn(session)
            mark_task_ran(name, time.monotonic())
            mark_idle_task_done()
            if done:
                logger.info("Idle: задача %s выполнена", name)
            else:
                logger.debug("Idle: задача %s — нечего делать", name)
        except EmptyArchiveError:
            mark_task_ran(name, time.monotonic())
        except ModelAsleepError:
            logger.info("Idle: модель занята/спит — %s отложена", name)
        except Exception:
            logger.exception("Idle: ошибка в задаче %s", name)
            mark_task_ran(name, time.monotonic())


def start_idle_worker() -> None:
    global _worker_task
    if _worker_task and not _worker_task.done():
        return
    _stop.clear()
    _worker_task = asyncio.create_task(idle_worker_loop(), name="hvk-idle-worker")


async def stop_idle_worker() -> None:
    global _worker_task
    _stop.set()
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    _worker_task = None


async def idle_status() -> dict:
    settings = get_settings()
    snap = await snapshot(quiet_seconds=settings.idle_quiet_seconds)
    free = await max_free_vram_mb()
    return {
        "enabled": settings.idle_worker_enabled,
        **snap,
        "vram_free_mb": free,
    }

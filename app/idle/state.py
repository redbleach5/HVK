"""Состояние занятости: чат/стол vs фоновое улучшение."""

from __future__ import annotations

import asyncio
import time

_lock = asyncio.Lock()
_active_llm: int = 0
_llm_gate = asyncio.Lock()
_last_user_activity: float = 0.0
_last_idle_task_at: float = 0.0


def touch_activity() -> None:
    """Пользователь или активный запрос — модель для себя."""
    global _last_user_activity
    _last_user_activity = time.monotonic()


async def llm_enter() -> None:
    global _active_llm
    await _llm_gate.acquire()
    async with _lock:
        _active_llm += 1
    touch_activity()


async def llm_leave() -> None:
    global _active_llm
    async with _lock:
        _active_llm = max(0, _active_llm - 1)
    _llm_gate.release()


async def snapshot(*, quiet_seconds: float) -> dict[str, float | int | bool]:
    async with _lock:
        active = _active_llm
        last_act = _last_user_activity
        last_task = _last_idle_task_at
    now = time.monotonic()
    quiet_for = now - last_act if last_act else 9999.0
    return {
        "active_llm": active,
        "quiet_for_s": round(quiet_for, 1),
        "idle": active == 0 and quiet_for >= quiet_seconds,
        "last_idle_task_ago_s": round(now - last_task, 1) if last_task else None,
    }


async def is_idle(*, quiet_seconds: float) -> bool:
    snap = await snapshot(quiet_seconds=quiet_seconds)
    return bool(snap["idle"])


def mark_idle_task_done() -> None:
    global _last_idle_task_at
    _last_idle_task_at = time.monotonic()

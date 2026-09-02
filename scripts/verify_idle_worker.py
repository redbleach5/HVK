# -*- coding: utf-8 -*-
"""Idle worker: busy gate, task registry, no LLM when active."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.idle.state import is_idle, llm_enter, llm_leave, snapshot, touch_activity  # noqa: E402
from app.idle.tasks import IDLE_TASKS, pick_next_task  # noqa: E402


async def main() -> None:
    touch_activity()
    if await is_idle(quiet_seconds=55.0):
        raise SystemExit("should not be idle right after touch")

    await llm_enter()
    if await is_idle(quiet_seconds=1.0):
        raise SystemExit("should not be idle while llm active")
    await llm_leave()

    snap = await snapshot(quiet_seconds=55.0)
    if snap["active_llm"] != 0:
        raise SystemExit("active_llm leak")

    if pick_next_task(999999.0) is None:
        raise SystemExit("pick_next_task returned nothing on fresh clock")

    names = {t[0] for t in IDLE_TASKS}
    for need in ("sync_themes", "audience_cache", "ideas_warm", "voice_stale"):
        if need not in names:
            raise SystemExit(f"missing idle task {need}")

    print("verify_idle_worker ok")
    print(f"  tasks={len(IDLE_TASKS)} snapshot={snap}")


if __name__ == "__main__":
    asyncio.run(main())

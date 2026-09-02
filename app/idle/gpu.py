"""Проверка VRAM — не грузить вторую модель, если памяти мало."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def max_free_vram_mb() -> int | None:
    """Свободная VRAM на самой свободной карте. None — nvidia-smi недоступен."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "nvidia-smi",
            "--query-gpu=memory.free",
            "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8.0)
        vals: list[int] = []
        for line in stdout.decode(errors="ignore").splitlines():
            chunk = line.strip().split()[0] if line.strip() else ""
            if chunk.isdigit():
                vals.append(int(chunk))
        return max(vals) if vals else None
    except Exception:
        logger.debug("nvidia-smi недоступен", exc_info=True)
        return None


async def vram_allows_llm(*, min_free_mb: int, brain_loaded: bool) -> bool:
    """Модель уже в VRAM — можно дорабатывать. Иначе нужен запас памяти."""
    if brain_loaded:
        return True
    free = await max_free_vram_mb()
    if free is None:
        return True
    return free >= min_free_mb

"""Кольцевой буфер метрик вызовов модели — без БД, для живой диагностики."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

_MAX = 80
_lock = asyncio.Lock()
_calls: deque[dict[str, Any]] = deque(maxlen=_MAX)


@dataclass
class LlmCallMetric:
    kind: str
    label: str
    duration_ms: float
    ok: bool
    error: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


async def record_call(metric: LlmCallMetric) -> None:
    async with _lock:
        _calls.append(asdict(metric))


async def recent_calls(limit: int = 40) -> list[dict[str, Any]]:
    async with _lock:
        items = list(_calls)
    return items[-limit:]


async def latency_summary(*, kind: str | None = None, label: str | None = None) -> dict[str, Any]:
    async with _lock:
        items = list(_calls)
    if kind:
        items = [x for x in items if x.get("kind") == kind]
    if label:
        items = [x for x in items if x.get("label") == label]
    ok_items = [x for x in items if x.get("ok")]
    fail = len(items) - len(ok_items)
    durations = sorted(float(x.get("duration_ms") or 0) for x in ok_items)
    if not durations:
        return {"n": len(items), "fail": fail, "p50_ms": None, "p95_ms": None}
    p50 = durations[len(durations) // 2]
    p95 = durations[max(0, int(len(durations) * 0.95) - 1)]
    return {"n": len(items), "fail": fail, "p50_ms": round(p50), "p95_ms": round(p95)}

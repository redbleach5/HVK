"""Короткие пробы JSON-пути — не полный агент."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from pydantic import BaseModel

from app.llm.client import get_llm
from app.llm.exceptions import ModelAsleepError

logger = logging.getLogger(__name__)

_last_probe_at: datetime | None = None
_last_probe_ms: float | None = None
_last_probe_ok: bool | None = None


class _PingJson(BaseModel):
    status: str


async def json_path_probe(*, force: bool = False, min_interval_s: float = 14_400) -> dict:
    """Микро-JSON через complete_json. Не чаще раза в 4 ч, если не force."""
    global _last_probe_at, _last_probe_ms, _last_probe_ok
    now = datetime.now(timezone.utc)
    if (
        not force
        and _last_probe_at is not None
        and (now - _last_probe_at).total_seconds() < min_interval_s
    ):
        return {
            "skipped": True,
            "ok": _last_probe_ok,
            "duration_ms": _last_probe_ms,
            "at": _last_probe_at.isoformat(),
        }

    t0 = time.perf_counter()
    ok = False
    err = ""
    try:
        out = await get_llm().complete_json(
            system="Ответь одним JSON-объектом.",
            user='Верни {"status":"ok"} — поле status должно быть строкой "ok".',
            schema=_PingJson,
            max_tokens=64,
            label="probe_json",
        )
        ok = (out.status or "").strip().lower() == "ok"
    except ModelAsleepError as exc:
        err = str(exc)
    except Exception as exc:
        err = str(exc)[:200]
        logger.info("json_path_probe failed: %s", exc)

    ms = round((time.perf_counter() - t0) * 1000, 1)
    _last_probe_at = now
    _last_probe_ms = ms
    _last_probe_ok = ok and not err
    return {
        "skipped": False,
        "ok": _last_probe_ok,
        "duration_ms": ms,
        "error": err or None,
        "at": now.isoformat(),
    }

# -*- coding: utf-8 -*-
"""Самодиагностика: endpoint, метрики, пробы. Без полного E2E."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

API = "http://127.0.0.1:8080"


async def _api(path: str, **params: bool) -> dict:
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.get(f"{API}{path}", params=params)
        r.raise_for_status()
        return r.json()


async def main() -> None:
    health = await _api("/health")
    if "brain" not in health:
        raise SystemExit("GET /health: нет поля brain")

    diag = await _api("/health/diagnostics", probe=False, insight=False, refresh=True)
    for key in ("ok", "checked_at", "issues", "checks", "chat_latency", "json_latency"):
        if key not in diag:
            raise SystemExit(f"GET /health/diagnostics: нет поля {key}")

    cached = await _api("/health/diagnostics", refresh=False)
    if cached.get("checked_at") != diag.get("checked_at"):
        raise SystemExit("refresh=false не вернул кэш last_report")

    # in-process: metrics + probe module import
    from app.diagnostics.metrics import LlmCallMetric, latency_summary, record_call  # noqa: E402
    from app.diagnostics.probes import json_path_probe  # noqa: E402
    from app.diagnostics.engine import run_diagnostics  # noqa: E402
    from app.db.session import SessionLocal  # noqa: E402

    await record_call(
        LlmCallMetric(kind="stream", label="chat", duration_ms=1200.0, ok=True)
    )
    lat = await latency_summary(kind="stream", label="chat")
    if int(lat.get("n") or 0) < 1:
        raise SystemExit("latency_summary не видит записанный вызов")

    async with SessionLocal() as session:
        report = await run_diagnostics(session, probe=False, insight=False)
    if not report.checked_at:
        raise SystemExit("run_diagnostics: пустой checked_at")

    print("verify_diagnostics ok")
    print(f"  brain={health.get('brain')} issues={diag.get('issues')}")
    if report.author_hint:
        print(f"  author_hint={report.author_hint[:80]}...")


if __name__ == "__main__":
    asyncio.run(main())

# -*- coding: utf-8 -*-
"""Практическая проверка idle worker + JSON-агентов. Долго, но без обрыва."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

API = "http://127.0.0.1:8080"
QUIET_WAIT = 70  # > idle_quiet_seconds (55)
POLL = 8


async def wait_api(client: httpx.AsyncClient, timeout: float = 60.0) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = await client.get("/health", timeout=5.0)
            if r.status_code == 200:
                return
        except Exception:
            pass
        await asyncio.sleep(2)
    raise SystemExit("API не поднялся")


async def get_diag(client: httpx.AsyncClient) -> dict:
    r = await client.get(
        "/health/diagnostics",
        params={"probe": "false", "insight": "false", "refresh": "true"},
        timeout=120.0,
    )
    r.raise_for_status()
    return r.json()


async def main() -> None:
    async with httpx.AsyncClient(base_url=API, timeout=httpx.Timeout(900.0, connect=15.0)) as client:
        await wait_api(client)
        print("=== 1. API up ===")

        d0 = await get_diag(client)
        idle_check = next((c for c in d0.get("checks", []) if c.get("id") == "idle_worker"), None)
        if idle_check is None:
            raise SystemExit("idle_worker нет в diagnostics — API без нового кода?")
        print(f"idle_worker at start: enabled={idle_check.get('enabled')} idle={idle_check.get('idle')}")

        print(f"=== 2. Жду {QUIET_WAIT}s простоя (не трогаю API) ===")
        await asyncio.sleep(QUIET_WAIT)

        seen_idle_tasks: list[str] = []
        t_watch = time.time()
        while time.time() - t_watch < 600:
            d = await get_diag(client)
            ic = next((c for c in d.get("checks", []) if c.get("id") == "idle_worker"), {})
            if ic.get("idle"):
                print(
                    f"  idle ok: quiet={ic.get('quiet_for_s')}s "
                    f"last_task_ago={ic.get('last_idle_task_ago_s')}"
                )

            if ic.get("last_idle_task_ago_s") is not None and ic.get("last_idle_task_ago_s", 999) < 180:
                print(f"  idle task ran recently ({ic.get('last_idle_task_ago_s')}s ago)")
                break
            await asyncio.sleep(POLL)

        d1 = await get_diag(client)
        ic1 = next((c for c in d1.get("checks", []) if c.get("id") == "idle_worker"), {})
        if ic1.get("last_idle_task_ago_s") is None:
            print("WARN: idle task не зафиксирован за 10 мин — смотри logs/api.log")
        else:
            print(f"PASS idle: last_task_ago={ic1.get('last_idle_task_ago_s')}s vram={ic1.get('vram_free_mb')}")

        print("=== 3. JSON: ideas/generate (count=2) ===")
        t0 = time.time()
        r = await client.post("/ideas/generate", json={"count": 2})
        dt = time.time() - t0
        print(f"ideas_generate: {r.status_code} in {dt:.1f}s")
        if r.status_code >= 400:
            raise SystemExit(r.text[:400])
        ideas = r.json().get("ideas") or []
        if len(ideas) < 1:
            raise SystemExit("ideas пусто")
        print(f"  got {len(ideas)} ideas, first: {(ideas[0].get('theme') or '')[:60]}")

        print("=== 4. JSON: analytics with_report ===")
        t0 = time.time()
        r = await client.get("/analytics", params={"with_report": "true"})
        dt = time.time() - t0
        print(f"analytics_report: {r.status_code} in {dt:.1f}s")
        if r.status_code >= 400:
            raise SystemExit(r.text[:400])
        rep = r.json().get("report")
        if not rep or not (rep.get("portrait") or "").strip():
            raise SystemExit("analytics report empty")
        print(f"  portrait: {(rep.get('portrait') or '')[:80]}...")

        print("=== 5. analytics cache (2nd call instant) ===")
        t0 = time.time()
        r2 = await client.get("/analytics", params={"with_report": "true"})
        dt2 = time.time() - t0
        print(f"analytics_cached: {r2.status_code} in {dt2:.1f}s")
        if dt2 > 15:
            print("WARN: cache miss? expected <15s")

        print("\n=== ALL PRACTICE CHECKS OK ===")


if __name__ == "__main__":
    asyncio.run(main())

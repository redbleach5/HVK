# -*- coding: utf-8 -*-
"""Где именно verify_vk упирается в таймаут: по одному вызову с таймингом.

Запуск: C:\\HVK\\.venv\\Scripts\\python.exe scripts\\_probe_vk_latency.py

Ничего не меняет в архиве, кроме POST /onboarding/import-vk — он читает
стену VK. Каждый шаг печатает статус и секунды, чтобы понять: медленный
сам VK или это наш таймаут в 20 с.
"""

from __future__ import annotations

import sys
import time

import httpx

API = "http://127.0.0.1:8080"


def timed(client: httpx.Client, method: str, path: str, **kwargs) -> None:
    start = time.time()
    try:
        resp = client.request(method, path, **kwargs)
        body = ""
        try:
            body = str(resp.json())[:200]
        except Exception:
            body = resp.text[:200]
        print(f"{method} {path}: {resp.status_code} за {time.time() - start:.1f}с {body}")
    except Exception as exc:
        print(f"{method} {path}: ПРОВАЛ за {time.time() - start:.1f}с {type(exc).__name__}: {exc}")


def main() -> int:
    timeout = httpx.Timeout(120.0, connect=15.0)
    with httpx.Client(base_url=API, timeout=timeout) as c:
        timed(c, "GET", "/onboarding/status")
        timed(c, "GET", "/concierge/inbox", params={"limit": 5})
        timed(c, "GET", "/archive/search", params={"q": "чай"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
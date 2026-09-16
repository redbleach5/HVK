# -*- coding: utf-8 -*-
"""Живая проверка поднятого стека: только чтение, ничего не пишет.

Запуск: C:\\HVK\\.venv\\Scripts\\python.exe scripts\\_probe_live_stack.py

Проверяет /health, /onboarding/status, /voice и /archive/search — то есть
новый чанковый nomic-поиск через настоящий API. Ни одной LLM-генерации и
ни одной записи в data/app.db: архив автора не меняется (в отличие от
scripts/smoke_product.py, который заливает тестовые посты).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8080"
UI = "http://127.0.0.1:8501"
QUERIES = ("гардероб", "рецепт выпечки", "дочь", "чай в любимой чашке")


def main() -> int:
    problems: list[str] = []

    def fail(text: str) -> None:
        problems.append(text)
        print(f"ПРОВАЛ: {text}")

    with httpx.Client(base_url=API, timeout=httpx.Timeout(20.0, read=300.0)) as c:
        try:
            data = c.get("/health").raise_for_status().json()
            print(
                f"[health] ok={data.get('ok')} brain={data.get('brain')} "
                f"eyes={data.get('eyes')} vk={data.get('vk_configured')} "
                f"msg={data.get('message')}"
            )
            if not data.get("ok"):
                fail("health.ok = false: мозг недоступен")
        except Exception as exc:
            fail(f"/health не ответил: {type(exc).__name__}: {exc}")

        for path in ("/onboarding/status", "/voice"):
            try:
                payload = c.get(path).raise_for_status().json()
                print(f"[{path}] {json.dumps(payload, ensure_ascii=False)[:300]}")
            except Exception as exc:
                fail(f"{path} не ответил: {type(exc).__name__}: {exc}")

        for q in QUERIES:
            try:
                payload = c.get("/archive/search", params={"q": q}).raise_for_status().json()
                hits = payload.get("hits") or []
                top = [
                    (h.get("post_id"), h.get("theme"), (h.get("text_preview") or "")[:40])
                    for h in hits[:3]
                ]
                print(f"[archive/search {q!r}] hits={len(hits)} top={top}")
                if not hits:
                    fail(f"поиск {q!r} не вернул ни одного поста")
            except Exception as exc:
                fail(f"/archive/search {q!r}: {type(exc).__name__}: {exc}")

    try:
        code = httpx.get(UI, timeout=10.0).status_code
        print(f"[ui :8501] {code}")
        if code != 200:
            fail(f"UI вернул {code}")
    except Exception as exc:
        fail(f"UI не ответил: {type(exc).__name__}: {exc}")

    print()
    if problems:
        for item in problems:
            print("ПРОВАЛ:", item)
        return 1
    print("ОК: стек живой, поиск отвечает постами, архив не тронут")
    return 0


if __name__ == "__main__":
    sys.exit(main())
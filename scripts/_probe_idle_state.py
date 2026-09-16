# -*- coding: utf-8 -*-
"""Состояние занятости LLM: не держит ли кто-то глобальный llm_gate.

Запуск: C:\\HVK\\.venv\\Scripts\\python.exe scripts\\_probe_idle_state.py

Только чтение: /health/diagnostics с probe=false&insight=false (LLM не зовёт)
и `ollama ps`. Если active_llm > 0, а Ollama пуста — лок llm_gate утёк, и все
LLM-запросы висят до таймаута.
"""

from __future__ import annotations

import json
import subprocess
import sys

import httpx

API = "http://127.0.0.1:8080"


def ollama_running() -> list[str]:
    try:
        out = subprocess.run(
            ["ollama", "ps"], capture_output=True, text=True, timeout=60
        ).stdout
    except Exception as exc:  # noqa: BLE001
        return [f"ollama ps недоступен: {exc}"]
    return [line.strip() for line in out.splitlines()[1:] if line.strip()]


def main() -> int:
    r = httpx.get(
        f"{API}/health/diagnostics",
        params={"probe": "false", "insight": "false", "refresh": "true"},
        timeout=120.0,
    )
    r.raise_for_status()
    data = r.json()
    idle = next((c for c in data.get("checks", []) if c.get("id") == "idle_worker"), {})
    print("idle_worker:", json.dumps(idle, ensure_ascii=False))
    for check in data.get("checks", []):
        if check.get("status") == "warn":
            print("warn:", check.get("id"), "-", (check.get("message") or "")[:200])

    models = ollama_running()
    print("ollama ps:", models or "(пусто — ничего не загружено)")
    active = int(idle.get("active_llm") or 0)
    if active > 0 and not models:
        print()
        print("ТРЕВОГА: active_llm > 0, но Ollama пуста — лок llm_gate висит.")
        return 1
    if active > 0:
        print()
        print(f"active_llm={active}: LLM сейчас занята (возможно, idle-задача).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
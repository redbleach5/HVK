# -*- coding: utf-8 -*-
"""Живой API: health, интенты, поиск не ломает маршруты."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

API = "http://127.0.0.1:8080"


def main() -> None:
    with httpx.Client(base_url=API, timeout=15.0) as client:
        health = client.get("/health")
        health.raise_for_status()
        body = health.json()
        if not body.get("ok"):
            raise SystemExit(f"health not ok: {body}")

        threads = client.get("/chat/threads")
        threads.raise_for_status()
        if not threads.json().get("threads"):
            raise SystemExit("no chat threads")

        cases = [
            ("привет", "general"),
            ("сегодня", "today"),
            ("идеи", "ideas"),
            ("план", "plan"),
            ("погугли погоду в Москве", "general"),
        ]
        for text, expected in cases:
            resp = client.post("/chat/intent", json={"message": text, "has_photos": False})
            resp.raise_for_status()
            got = resp.json().get("intent")
            if got != expected:
                raise SystemExit(f"{text!r} intent={got}, expected {expected}")

    print("VERIFY CHAT API OK")


if __name__ == "__main__":
    main()

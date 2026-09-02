# -*- coding: utf-8 -*-
"""Живой чат: стрим мысли + tool calling поиска. Не трогает архив."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "_verify_chat_live.json"
API = "http://127.0.0.1:8080"
MESSAGE = "https://t.me/AshihminaDaria - вот ссылка. Посмотри"


def main() -> int:
    report: dict = {"ok": False, "message": MESSAGE}
    timeout = httpx.Timeout(300.0, connect=10.0)
    kinds: list[str] = []
    thinking = ""
    text = ""
    search_q: list[str] = []
    done: dict = {}

    with httpx.Client(base_url=API, timeout=timeout) as client:
        health = client.get("/health")
        health.raise_for_status()
        report["health"] = health.json().get("ok")

        with client.stream("POST", "/chat/stream", data={"message": MESSAGE}) as resp:
            report["status"] = resp.status_code
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                ev = json.loads(line)
                kind = ev.get("t")
                kinds.append(kind)
                if kind == "thinking":
                    thinking += ev.get("d") or ""
                elif kind == "text":
                    text += ev.get("d") or ""
                elif kind == "search":
                    search_q.append(ev.get("q") or "")
                elif kind == "done":
                    done = ev

    reply = (done.get("reply") or text or "").strip()
    cards = done.get("cards") or []
    card_types = [c.get("type") for c in cards if isinstance(c, dict)]
    low = reply.lower()
    refused = any(
        s in low
        for s in (
            "не умею интернет",
            "не открываю",
            "ссылки не открываю",
            "в телеграм не захожу",
            "интернет не листаю",
            "вообще не умею",
        )
    )

    report.update(
        {
            "kinds": kinds,
            "think_chars": len(thinking),
            "text_chars": len(text),
            "search_q": search_q,
            "card_types": card_types,
            "reply_preview": reply[:400],
            "refused_internet": refused,
        }
    )

    errors: list[str] = []
    if "done" not in kinds:
        errors.append("no done")
    if len(thinking) < 80:
        errors.append(f"thinking too short: {len(thinking)}")
    if len(reply) < 40:
        errors.append("empty reply")
    if refused:
        errors.append("model refused internet")
    if not search_q and "web" not in card_types:
        errors.append("no tool search")

    report["errors"] = errors
    report["ok"] = not errors
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    print("think_chars", len(thinking), "text_chars", len(text), "search", search_q)
    print("cards", card_types)
    print("reply", reply[:240].replace("\n", " "))
    if errors:
        print("FAIL", errors)
        return 1
    print("VERIFY CHAT LIVE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

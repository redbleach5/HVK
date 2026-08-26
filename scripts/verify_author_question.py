"""Live check: same author question is a conversation, not an edit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "scripts" / "_verify_question.json"
API = "http://127.0.0.1:8080"

QUESTION = (
    "Кажется, я уже писала про осенний гардероб и мамин рецепт. "
    "Что лучше выложить в сообщество сейчас, чтобы не повторяться? "
    "Хочется тихое, про дом и дочку, без рекламы. И объясни почему именно это."
)


def main() -> None:
    report: dict = {"ok": False}
    timeout = httpx.Timeout(connect=20.0, read=None, write=120.0, pool=20.0)
    with httpx.Client(base_url=API, timeout=timeout) as client:
        status = client.get("/onboarding/status")
        status.raise_for_status()
        report["onboarding"] = status.json()
        today = client.get("/today")
        today.raise_for_status()
        digest = today.json().get("digest") or ""
        report["today_digest"] = digest[:400]
        blob = digest.lower()
        report["today_has_promo"] = any(
            m in blob for m in ("кэшбэк", "кэшбек", "zarina", "pstpnr")
        )
        client.delete("/chat/history")
        kinds: list[str] = []
        think = ""
        text = ""
        done: dict = {}
        with client.stream("POST", "/chat/stream", data={"message": QUESTION}) as response:
            report["stream_status"] = response.status_code
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                ev = json.loads(line)
                kind = ev.get("t")
                kinds.append(kind)
                if kind == "thinking":
                    think += ev.get("d") or ""
                elif kind == "text":
                    text += ev.get("d") or ""
                elif kind == "done":
                    done = ev
        report["kinds"] = kinds
        report["thinking_n"] = len(think)
        report["intent"] = done.get("intent")
        report["reply"] = done.get("reply") or text
        report["card_types"] = [
            (c or {}).get("type") for c in (done.get("cards") or []) if isinstance(c, dict)
        ]

    reply = (report.get("reply") or "").lower()
    cards = report.get("card_types") or []
    fail = ""
    if report["today_has_promo"]:
        fail = "today cites promo"
    elif not kinds or kinds[0] != "open":
        fail = f"no open event: {kinds[:4]}"
    elif report["intent"] == "edit" or "edit" in cards:
        fail = "still routed to edit"
    elif "в голосе." in reply[:40]:
        fail = "editor voice-check reply"
    elif "юля" in reply and "уснула на диване" in reply:
        fail = "ghostwritten julia post"
    elif not (report.get("reply") or "").strip():
        fail = "empty reply"
    report["fail"] = fail
    report["ok"] = not fail
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    print("ok", report["ok"], "intent", report.get("intent"), "fail", fail or "-")


if __name__ == "__main__":
    main()

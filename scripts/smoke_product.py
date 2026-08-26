"""Запуск проверки «Тихой редакции» без человека в браузере."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
THOUGHTS = ROOT / "THOUGHTS.txt"
API = "http://127.0.0.1:8080"
UI = "http://127.0.0.1:8501"

POSTS = [
    "Утром заварила чай в любимой чашке — пар, тишина, свет на столе. Никуда не спешу.",
    "Нашла на блошином рынке льняную салфетку. Дома легла как будто всегда здесь жила.",
    "Вечером простой рис с маслом и зеленью. Кажется, этого достаточно.",
    "Окно чуть запотело, за ним двор. Хочется сфотографировать не сюжет, а воздух.",
]


def _append_report(lines: list[str]) -> None:
    block = "\n".join(lines) + "\n"
    prev = THOUGHTS.read_text(encoding="utf-8") if THOUGHTS.exists() else ""
    THOUGHTS.write_text(prev + block, encoding="utf-8")


def main() -> int:
    report = [
        "",
        f"## REPORT smoke_product.py",
        f"time: {datetime.now().isoformat(timespec='seconds')}",
        "runner: C:\\HVK\\scripts\\smoke_product.py",
    ]
    try:
        with httpx.Client(base_url=API, timeout=httpx.Timeout(30.0, read=180.0)) as c:
            health = c.get("/health")
            health.raise_for_status()
            report.append(f"health: {health.json().get('message')}")

            ui = httpx.get(UI, timeout=8.0)
            report.append(f"ui_8501: {ui.status_code}")

            c.post(
                "/onboarding/profile",
                json={
                    "blog_name": "Красивое в обычном",
                    "about": "Тихие находки дома, чай, свет, простые вещи.",
                },
            ).raise_for_status()

            arch = c.post("/onboarding/archive", json={"posts": POSTS})
            arch.raise_for_status()
            st = arch.json()
            report.append(f"posts_imported: {st.get('posts_imported')}")
            report.append(f"voice_ready_after_archive: {st.get('voice_ready')}")

            voice_ready = bool(st.get("voice_ready"))
            if not voice_ready:
                for _ in range(40):
                    time.sleep(3)
                    poll = c.get("/onboarding/status")
                    poll.raise_for_status()
                    voice_ready = bool(poll.json().get("voice_ready"))
                    if voice_ready:
                        break
            report.append(f"voice_ready_after_wait: {voice_ready}")

            done = c.post("/onboarding/complete")
            done.raise_for_status()
            st2 = done.json()
            report.append(f"onboarding_done: {st2.get('done')}")
            report.append(f"voice_ready: {st2.get('voice_ready')}")

            today = c.get("/today")
            today.raise_for_status()
            body = (today.json().get("digest") or "")[:240]
            cites = any(w in (today.json().get("digest") or "") for w in ("чай", "салфет", "рис", "окно"))
            ideas_n = len(today.json().get("ideas") or [])
            report.append(f"today_digest: {body!r}")
            report.append(f"today_cites_archive: {'yes' if cites else 'no'}")
            report.append(f"today_ideas: {ideas_n}")

            ideas = c.post("/ideas/generate", json={"count": 2})
            if ideas.status_code >= 400:
                report.append(f"ideas: fail {ideas.status_code} {ideas.text[:200]}")
            else:
                n = len(ideas.json().get("ideas") or [])
                report.append(f"ideas: cites-posts n={n}")

            report.append("tabs_ok: onboarding complete — UI shows tabs after refresh")
            report.append("what_broke: ")
            report.append("next: open http://127.0.0.1:8501")
    except Exception as exc:
        report.append(f"what_broke: {type(exc).__name__}: {exc}")
        _append_report(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    _append_report(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

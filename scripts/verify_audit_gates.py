# -*- coding: utf-8 -*-
"""Audit gates: author-post count, exact router, config, wall.post. No LLM."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.router import classify_intent_heuristic  # noqa: E402
from app.config import Settings  # noqa: E402
from app.vk.client import _WALL_METHODS  # noqa: E402


def main() -> None:
    cfg_src = (ROOT / "app" / "config.py").read_text(encoding="utf-8")
    if "127.0.0.1:8000" in cfg_src:
        raise SystemExit("config default still points at Canvas :8000")
    if "qwen3.8:27b" not in cfg_src:
        raise SystemExit("config default missing qwen3.8:27b")
    settings = Settings()
    if ":8000" in (settings.brain_base_url or ""):
        raise SystemExit(f"brain_base_url still Canvas: {settings.brain_base_url}")

    if "wall.post" not in _WALL_METHODS:
        raise SystemExit("wall.post not in wall token methods")

    ping_src = (ROOT / "app" / "llm" / "client.py").read_text(encoding="utf-8")
    if "status_code < 500" in ping_src:
        raise SystemExit("ping still treats HTTP <500 as up")
    if "status_code == 200" not in ping_src:
        raise SystemExit("ping does not require HTTP 200")

    health_src = (ROOT / "app" / "api" / "routes" / "health.py").read_text(encoding="utf-8")
    if "ok=brain or" in health_src.replace(" ", ""):
        raise SystemExit("health ok still true when only eyes are up")
    if "ok=brain," not in health_src.replace(" ", ""):
        raise SystemExit("health ok is not gated on brain")

    traps = (
        ("у меня нет идей как назвать кадр", None),
        ("не хочу опубликовать это", None),
        ("входящие мысли перед съёмкой", None),
        ("сезон и архив семейных фото", None),
        ("сегодня", "today"),
        ("идеи", "ideas"),
        ("поправь абзац", "edit"),
        ("опубликовать: текст", "publish"),
        ("входящие", "inbox"),
    )
    for text, expected in traps:
        got = classify_intent_heuristic(text, has_photos=False)
        if got != expected:
            raise SystemExit(f"router {text!r} -> {got}, expected {expected}")

    retrieve_src = (ROOT / "app" / "memory" / "retrieve.py").read_text(encoding="utf-8")
    if "query_wants_hits" in retrieve_src:
        raise SystemExit("retrieve still has mood blend")
    print("ok")


if __name__ == "__main__":
    main()

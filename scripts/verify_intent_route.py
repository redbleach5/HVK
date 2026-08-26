"""Verify intent routing and ad-free digest. No LLM."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.chat import classify_intent_heuristic  # noqa: E402
from app.memory.citations import digest_from_posts  # noqa: E402
from app.memory.themes import is_promotional  # noqa: E402

QUESTION = (
    "Кажется, я уже писала про осенний гардероб и мамин рецепт. "
    "Что лучше выложить в сообщество сейчас, чтобы не повторяться? "
    "Хочется тихое, про дом и дочку, без рекламы. И объясни почему именно это."
)

DRAFT = (
    "Кажется, пора потихоньку доставать осенний гардероб. "
    "После рождения дочки мой стиль очень поменялся, поэтому я выбираю вещи иначе. "
    "Начала разбор с любимого трикотажа."
)


def main() -> None:
    intent = classify_intent_heuristic(QUESTION, has_photos=False)
    if intent == "edit":
        raise SystemExit("question still routed to edit")
    if intent is not None:
        raise SystemExit(f"question routed to {intent}, expected general stream")

    draft_intent = classify_intent_heuristic(DRAFT, has_photos=False)
    if draft_intent != "edit":
        raise SystemExit(f"draft routed to {draft_intent}, expected edit")

    if not is_promotional("Карбокситерапия! КЭШБЭК 65% Цена на ВБ - 900"):
        raise SystemExit("promo marker missed")
    if is_promotional("Любимый мамин рецепт. Есть блюда, которые готовишь дома."):
        raise SystemExit("real post marked promo")

    posts = [
        SimpleNamespace(text="Кажется, пора доставать осенний гардероб", theme="кадр"),
        SimpleNamespace(text="КЭШБЭК 65% Цена на ВБ - 900. Количество ограничено!!!", theme="дом"),
        SimpleNamespace(text="Любимый мамин рецепт: тортильи, яйцо, сыр", theme="еда"),
        SimpleNamespace(text="", theme="без текста"),
    ]
    body, bits = digest_from_posts(posts)
    blob = body.lower()
    if "кэшбэк" in blob or "кэшбек" in blob or "zarina" in blob:
        raise SystemExit("digest still cites promo")
    if "гардероб" not in blob or "рецепт" not in blob:
        raise SystemExit("digest lost author posts")
    if len(bits) != 2:
        raise SystemExit(f"digest bits={len(bits)}, expected 2")
    print("ok")


if __name__ == "__main__":
    main()

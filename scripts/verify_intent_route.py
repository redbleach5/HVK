"""Verify intent routing and ad-free digest. No LLM."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.chat import _CHAT_EDITOR, classify_intent_heuristic  # noqa: E402
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
    if "Сначала ответь на её слова" not in _CHAT_EDITOR:
        raise SystemExit("chat editor lost hear-first")
    if "Семью не суди" not in _CHAT_EDITOR:
        raise SystemExit("chat editor may judge the family")
    if "закрывай ворота" not in _CHAT_EDITOR:
        raise SystemExit("chat editor closed the kindness gate")
    if "Проницательность" not in _CHAT_EDITOR:
        raise SystemExit("chat editor lost perceptiveness")
    if "три строки" not in _CHAT_EDITOR:
        raise SystemExit("chat editor still offers unsolicited lines")
    if "Не выдумывай вещь" not in _CHAT_EDITOR:
        raise SystemExit("chat editor may invent objects")
    intent = classify_intent_heuristic(QUESTION, has_photos=False)
    if intent == "edit":
        raise SystemExit("question still routed to edit")
    if intent is not None:
        raise SystemExit(f"question routed to {intent}, expected general stream")

    talk_cases = (
        ("Какая идея лучше для сообщества?", None),
        ("Давай обсудим план съёмки чая", None),
        ("Какой сезонный пост лучше сегодня?", None),
        ("сегодня", "today"),
        ("идеи", "ideas"),
        ("план", "plan"),
        ("что лучше заходило в последнее время — и почему", None),
        ("хочу поправить текст", None),
        ("предложи идеи про чай", "ideas"),
        ("нет идей что постить", None),
        ("у меня нет идей как назвать этот кадр", None),
        ("я не хочу опубликовать это сегодня", None),
        ("разбираю входящие мысли перед съёмкой", None),
        ("в этом сезоне листаю архив семейных фото", None),
        ("поправь этот абзац про чай", "edit"),
        ("опубликовать: черновик", "publish"),
        ("входящие", "inbox"),
    )
    for text, expected in talk_cases:
        got = classify_intent_heuristic(text, has_photos=False)
        if got != expected:
            raise SystemExit(f"{text!r} routed to {got}, expected {expected}")

    draft_intent = classify_intent_heuristic(DRAFT, has_photos=False)
    if draft_intent is not None:
        raise SystemExit(f"draft routed to {draft_intent}, expected general")

    edit_cmd = classify_intent_heuristic("поправь\n" + DRAFT, has_photos=False)
    if edit_cmd != "edit":
        raise SystemExit(f"explicit edit routed to {edit_cmd}, expected edit")

    if not is_promotional("Карбокситерапия! КЭШБЭК 65% Цена на ВБ - 900"):
        raise SystemExit("promo marker missed")
    if not is_promotional("Запускаем новый розыгрыш. Приз: сертификат на 1000 рублей"):
        raise SystemExit("giveaway counted as author hit")
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

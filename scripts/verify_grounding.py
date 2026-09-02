"""Grounding helpers: citations, reader notes, no invented names in prompt. No LLM."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.base import SYSTEM_ASSISTANT  # noqa: E402
from app.agents.chat import plan_title_from_reply  # noqa: E402
from app.memory.citations import post_citation, reader_notes  # noqa: E402
from app.memory.store import _is_author_text  # noqa: E402


def main() -> None:
    if "не выдумывай" not in SYSTEM_ASSISTANT.lower() and "не выдумывай" not in SYSTEM_ASSISTANT:
        raise SystemExit("system prompt lost grounding")
    if "дочка" not in SYSTEM_ASSISTANT:
        raise SystemExit("system prompt missing name lock")
    if "черновик" not in SYSTEM_ASSISTANT:
        raise SystemExit("system prompt missing ghostwriter lock")

    post = SimpleNamespace(
        id=7,
        text="Не думала, что с началом самоприкорма мы будем принимать ванну несколько раз в день",
        theme="семья",
        comments=[{"text": "у нас так же было"}],
    )
    cite = post_citation(post)
    if "пост #7" not in cite:
        raise SystemExit(f"citation missing id: {cite}")
    notes = reader_notes(post)
    if "у нас так же" not in notes:
        raise SystemExit("reader notes missing")

    promo = SimpleNamespace(text="КЭШБЭК 65% Цена на ВБ", theme="жизнь")
    real = SimpleNamespace(text="Любимый мамин рецепт 🤍", theme="еда")
    if _is_author_text(promo):
        raise SystemExit("promo counted as author text")
    if not _is_author_text(real):
        raise SystemExit("real post rejected")

    title = plan_title_from_reply(
        "Слушай, давай так.\n\n**Двадцать минут тишины, пока дочка спит.**\n\nПочему именно это:",
        "что выложить",
    )
    if "тишины" not in title.lower() and "двадцать" not in title.lower():
        raise SystemExit(f"bad plan title: {title}")

    quoted = plan_title_from_reply(
        "Слушай, не надо.\n\n«Кажется, сегодня я на максимуме. Чай.»\n\nВсё.",
        "что лучше из того что у меня уже было?",
    )
    if "максимуме" in quoted.lower():
        raise SystemExit("quoted caption became plan title")
    print("ok")


if __name__ == "__main__":
    main()

"""Prompt budget: keep room for this turn's thinking. No LLM."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.chat import _format_history  # noqa: E402
from app.context.budget import (  # noqa: E402
    estimate_tokens,
    fit_user_prompt,
    generation_budget,
    prompt_budget,
)


def main() -> None:
    gen = generation_budget(think_tokens=2500, reply_tokens=2000)
    if gen != 4500:
        raise SystemExit(f"generation budget {gen}")
    room = prompt_budget(16384, gen)
    if room < 8000:
        raise SystemExit(f"prompt room too small: {room}")

    current = "Сообщение автора:\nчто выложить завтра?"
    user = (
        "фон " * 2000
        + "\n\nУЖЕ ОТКРЫТО В ЭТОМ ДИАЛОГЕ:\n"
        + ("старый пост " * 400)
        + "\n\nДОПОЛНИТЕЛЬНО:\n"
        + ("шум " * 400)
        + "\n\nНедавний диалог:\nпривет\n\n"
        + current
    )
    fitted = fit_user_prompt(user, max_tokens=1200)
    if "что выложить завтра" not in fitted:
        raise SystemExit("current question was dropped")
    if "УЖЕ ОТКРЫТО В ЭТОМ ДИАЛОГЕ" in fitted:
        raise SystemExit("session block was not compacted")
    if estimate_tokens(fitted) > estimate_tokens(user):
        raise SystemExit("fit grew the prompt")

    hist = _format_history(
        [
            {"role": "user", "content": "один " * 80},
            {"role": "assistant", "content": "два " * 80},
            {"role": "user", "content": "три " * 80},
            {"role": "assistant", "content": "четыре " * 80},
            {"role": "user", "content": "свежий вопрос про чай"},
        ]
    )
    if "Раньше в диалоге" not in hist:
        raise SystemExit("old turns were not compacted")
    if "свежий вопрос про чай" not in hist:
        raise SystemExit("recent turn missing")
    print("ok")


if __name__ == "__main__":
    main()

"""Working-set context: relevant posts in full, not a 400-char dump. No LLM."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.chat import _format_history  # noqa: E402
from app.context.engine import ContextEngine  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.memory.retrieve import posts_for_query  # noqa: E402
from app.memory.themes import is_promotional  # noqa: E402
from app.memory.working import clear_working, working_prompt  # noqa: E402

QUESTION = (
    "Кажется, я уже писала про осенний гардероб и мамин рецепт. "
    "Что лучше выложить в сообщество сейчас, чтобы не повторяться?"
)


async def main() -> None:
    clear_working()
    long_msg = "А" * 900
    hist = _format_history(
        [
            {"role": "user", "content": long_msg},
            {"role": "assistant", "content": "коротко"},
        ]
    )
    if len(hist) < 800:
        raise SystemExit("history still truncated too hard")

    async with SessionLocal() as session:
        posts = await posts_for_query(session, QUESTION, limit=6)
        if len(posts) < 2:
            raise SystemExit("retrieve returned too few posts")
        if any(is_promotional(p.text or "") for p in posts):
            raise SystemExit("retrieve returned promo")
        blob = " ".join((p.text or "") for p in posts).lower()
        if "гардероб" not in blob and "рецепт" not in blob and "доч" not in blob:
            raise SystemExit("retrieve missed author themes")

        engine = ContextEngine(session)
        context = await engine.build(query=QUESTION)
        if "ПО ЭТОМУ ВОПРОСУ" not in context:
            raise SystemExit("context missing retrieved block")
        if "кэшбэк" in context.lower() or "zarina" in context.lower():
            raise SystemExit("context cites promo")
        # Full texts, not 140-char stubs only
        marker = "ПО ЭТОМУ ВОПРОСУ"
        after = context.split(marker, 1)[1]
        if len(after) < 400:
            raise SystemExit("retrieved block too short")

    leftover = working_prompt()
    if "пост #" not in leftover and "пост #" not in context:
        raise SystemExit("working set empty")
    clear_working()
    print("ok")


if __name__ == "__main__":
    asyncio.run(main())

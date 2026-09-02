# -*- coding: utf-8 -*-
"""ROI squeeze: memory block that chat actually reads."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.base import SYSTEM_ASSISTANT  # noqa: E402
from app.context.engine import ContextEngine  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.memory.store import MemoryStore  # noqa: E402


async def main() -> None:
    if "Сначала услышь" not in SYSTEM_ASSISTANT:
        raise SystemExit("SYSTEM_ASSISTANT missing hear-first")
    if "помоги здесь же" not in SYSTEM_ASSISTANT:
        raise SystemExit("SYSTEM_ASSISTANT still shrinks the desk")
    if "не судья семьи" not in SYSTEM_ASSISTANT:
        raise SystemExit("SYSTEM_ASSISTANT may judge the family")
    if "Нет в тексте поста" not in SYSTEM_ASSISTANT:
        raise SystemExit("SYSTEM_ASSISTANT may invent objects")
    if "Формулировку" not in SYSTEM_ASSISTANT:
        raise SystemExit("SYSTEM_ASSISTANT still offers unsolicited lines")

    async with SessionLocal() as session:
        memory = MemoryStore(session)
        block = await memory.prompt_block()
        if "близкое по смыслу" not in block:
            raise SystemExit("prompt_block missing semantic antipathy")
        if "Сегодняшний голос" not in block and "Недавние посты важнее" not in block:
            raise SystemExit("prompt_block missing voice freshness")
        ctx = await ContextEngine(session).build(query="")
        if "даже другими словами" not in ctx:
            raise SystemExit("context missing paraphrase rule")
        lessons = await memory.recent_style_lessons(limit=4)
        blocked, matched = await memory.is_semantically_blocked("")
        if blocked:
            raise SystemExit("empty topic must not block")
        print(
            "ok",
            f"block_chars={len(block)}",
            f"style_lessons={len(lessons)}",
            f"empty_blocked={blocked}",
            f"matched={matched}",
        )


if __name__ == "__main__":
    asyncio.run(main())

# -*- coding: utf-8 -*-
"""Retry complete() to check intermittent empty."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal
from app.context.engine import ContextEngine
from app.llm.client import get_llm
from app.memory.store import MemoryStore


async def main() -> None:
    async with SessionLocal() as session:
        ctx = await ContextEngine(session).build()
        posts = await MemoryStore(session).recent_posts(3)
        snippets = "\n".join(f"— {p.theme}: {(p.text or '')[:120]}" for p in posts)
    user = f"{ctx}\n\n2 ideas JSON ideas[]\n{snippets}"[:6000]
    system = "JSON only. ideas array with theme field."
    llm = get_llm()
    for i in range(3):
        t0 = time.time()
        try:
            text = await llm.complete(
                system=system,
                user=user,
                max_tokens=1200,
                json_object=True,
                no_reasoning=True,
                label=f"retry{i}",
            )
            print(f"try {i+1} OK len={len(text)} in {round(time.time()-t0,1)}s")
        except Exception as exc:
            print(f"try {i+1} FAIL {type(exc).__name__} in {round(time.time()-t0,1)}s")


if __name__ == "__main__":
    asyncio.run(main())

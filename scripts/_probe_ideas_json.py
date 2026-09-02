# -*- coding: utf-8 -*-
"""Debug complete() on ideas-scale prompt."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pydantic import BaseModel, Field

from app.db.session import SessionLocal
from app.agents.ideas import _IdeaBatchLlm
from app.context.engine import ContextEngine
from app.llm.client import get_llm
from app.memory.store import MemoryStore


async def main() -> None:
    async with SessionLocal() as session:
        memory = MemoryStore(session)
        ctx = await ContextEngine(session).build()
        posts = await memory.recent_posts(3)
        snippets = "\n".join(f"— {p.theme}: {(p.text or '')[:120]}" for p in posts)
        user = f"""{ctx}

Нужно 2 идеи. JSON: {{ "ideas": [ ... ] }}.
Архив:
{snippets}
"""
        system = "Ты генератор идей. JSON only."
        llm = get_llm()
        t0 = time.time()
        try:
            out = await llm.complete_json(
                system=system,
                user=user,
                schema=_IdeaBatchLlm,
                max_tokens=1200,
                label="probe_ideas",
            )
            print("OK ideas", len(out.ideas), "in", round(time.time() - t0, 1), "s")
            if out.ideas:
                print(" first:", out.ideas[0].theme[:60])
        except Exception as exc:
            print("FAIL", type(exc).__name__, exc, "in", round(time.time() - t0, 1), "s")
            # raw complete
            t1 = time.time()
            raw = await llm.complete(
                system=system + "\nJSON: ideas[]",
                user=user,
                max_tokens=1200,
                json_object=True,
                no_reasoning=True,
                label="probe_raw",
            )
            print("raw len", len(raw), "in", round(time.time() - t1, 1), "s")
            print("raw head:", repr(raw[:400]))


if __name__ == "__main__":
    asyncio.run(main())

# -*- coding: utf-8
"""Full agent smoke — idle worker off to avoid Ollama contention."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

os.environ["IDLE_WORKER_ENABLED"] = "false"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings

get_settings.cache_clear()

from app.agents.audience import analyze_audience
from app.agents.ideas import generate_ideas
from app.db.session import SessionLocal


async def main() -> None:
    async with SessionLocal() as session:
        print("=== ideas ===")
        t0 = time.time()
        batch = await generate_ideas(session, count=2)
        print(f"ideas: {len(batch.ideas)} in {round(time.time()-t0,1)}s")
        for c in batch.ideas:
            print(" -", (c.theme or "")[:70])

        print("=== audience ===")
        t0 = time.time()
        rep = await analyze_audience(session)
        dt = round(time.time() - t0, 1)
        print(f"audience: {dt}s portrait={(rep.portrait or '')[:80]}...")

        print("=== audience cache ===")
        t0 = time.time()
        rep2 = await analyze_audience(session)
        print(f"cached: {round(time.time()-t0,1)}s")

    print("AGENTS OK")


if __name__ == "__main__":
    asyncio.run(main())

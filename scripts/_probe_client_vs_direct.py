# -*- coding: utf-8 -*-
"""Compare direct OpenAI vs LlmClient.complete on same payload."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.db.session import SessionLocal
from app.context.engine import ContextEngine
from app.llm.client import get_llm
from app.memory.store import MemoryStore


async def main() -> None:
    settings = get_settings()
    async with SessionLocal() as session:
        ctx = await ContextEngine(session).build()
        posts = await MemoryStore(session).recent_posts(3)
        snippets = "\n".join(f"— {p.theme}: {(p.text or '')[:120]}" for p in posts)
    user = f"{ctx}\n\n2 ideas JSON ideas[]\n{snippets}"[:6000]
    system = "JSON only. ideas array with theme field."

    client = AsyncOpenAI(base_url=settings.brain_base_url, api_key="not-needed", timeout=300.0)
    t0 = time.time()
    resp = await client.chat.completions.create(
        model=settings.brain_model,
        temperature=0.4,
        max_tokens=1200,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        extra_body={"think": False, "format": "json", "options": {"num_predict": 1200, "num_ctx": 8192}},
    )
    msg = resp.choices[0].message
    print("DIRECT content len", len(msg.content or ""), "in", round(time.time() - t0, 1), "s")

    llm = get_llm()
    t0 = time.time()
    try:
        text = await llm.complete(
            system=system,
            user=user,
            max_tokens=1200,
            json_object=True,
            no_reasoning=True,
            label="cmp",
        )
        print("CLIENT ok len", len(text), "in", round(time.time() - t0, 1), "s")
        print("head", repr(text[:200]))
    except Exception as exc:
        print("CLIENT fail", exc, "in", round(time.time() - t0, 1), "s")


if __name__ == "__main__":
    asyncio.run(main())

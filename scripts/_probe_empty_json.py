# -*- coding: utf-8 -*-
"""Dump full OpenAI-compat message when content empty."""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.db.session import SessionLocal
from app.context.engine import ContextEngine
from app.memory.store import MemoryStore


async def main() -> None:
    settings = get_settings()
    client = AsyncOpenAI(base_url=settings.brain_base_url, api_key="not-needed", timeout=300.0)
    async with SessionLocal() as session:
        ctx = await ContextEngine(session).build()
        posts = await MemoryStore(session).recent_posts(3)
        snippets = "\n".join(f"— {p.theme}: {(p.text or '')[:120]}" for p in posts)
    user = f"{ctx}\n\n2 ideas JSON ideas[]\n{snippets}"
    t0 = time.time()
    resp = await client.chat.completions.create(
        model=settings.brain_model,
        temperature=0.4,
        max_tokens=1200,
        messages=[
            {"role": "system", "content": "JSON only. ideas array."},
            {"role": "user", "content": user[:6000]},
        ],
        extra_body={"think": False, "format": "json", "options": {"num_predict": 1200, "num_ctx": 8192}},
    )
    print("elapsed", round(time.time() - t0, 1))
    msg = resp.choices[0].message
    print("content len", len(msg.content or ""))
    print("content head", repr((msg.content or "")[:300]))
    dump = msg.model_dump() if hasattr(msg, "model_dump") else {}
    print("keys", list(dump.keys()))
    for k, v in dump.items():
        if k == "content":
            continue
        if v:
            s = str(v)
            print(k, "len", len(s), "head", repr(s[:200]))


if __name__ == "__main__":
    asyncio.run(main())

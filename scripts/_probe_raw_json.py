# -*- coding: utf-8 -*-
"""Raw Ollama JSON response debug."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openai import AsyncOpenAI

from app.config import get_settings


async def main() -> None:
    settings = get_settings()
    client = AsyncOpenAI(base_url=settings.brain_base_url, api_key="not-needed", timeout=120.0)
    resp = await client.chat.completions.create(
        model=settings.brain_model,
        temperature=0.3,
        max_tokens=400,
        messages=[
            {"role": "system", "content": "Ответь СТРОГО одним JSON-объектом: {\"status\":\"ok\"}"},
            {"role": "user", "content": 'Верни JSON {"status":"ok"}'},
        ],
        extra_body={"think": False, "format": "json", "options": {"num_predict": 400}},
    )
    msg = resp.choices[0].message
    print("content:", repr((msg.content or "")[:500]))
    extra = getattr(msg, "model_extra", None)
    print("model_extra keys:", list(extra.keys()) if isinstance(extra, dict) else extra)
    if isinstance(extra, dict):
        for k in ("thinking", "reasoning_content", "reasoning"):
            if extra.get(k):
                print(k, repr(str(extra[k])[:200]))


if __name__ == "__main__":
    asyncio.run(main())

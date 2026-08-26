"""Verify native thinking stream + empty-archive chat path."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.llm.client import LlmClient  # noqa: E402


async def probe_client() -> None:
    llm = LlmClient()
    think_n = 0
    text_n = 0
    think = ""
    text = ""
    async for kind, piece in llm.stream_thoughtful(
        system="Think in Russian. Reply in Russian, one short sentence.",
        user="Say hello.",
        temperature=0.2,
        max_tokens=80,
    ):
        if kind == "thinking":
            think_n += 1
            think += piece
        else:
            text_n += 1
            text += piece
    print(f"client think_chunks={think_n} text_chunks={text_n}")
    print("think_preview", think[:160].replace("\n", " "))
    print("text_preview", text[:160].replace("\n", " "))
    if think_n == 0:
        raise SystemExit("no thinking deltas from LlmClient")


def probe_empty_archive() -> None:
    with httpx.Client(timeout=30.0) as client:
        with client.stream(
            "POST",
            "http://127.0.0.1:8080/chat/stream",
            data={"message": "help"},
        ) as response:
            response.raise_for_status()
            events = [json.loads(line) for line in response.iter_lines() if line]
    kinds = [e.get("t") for e in events]
    reply = (events[-1].get("reply") if events else "") or ""
    print("api kinds", kinds)
    print("api reply_preview", reply[:120].replace("\n", " "))
    if "done" not in kinds:
        raise SystemExit("chat stream did not finish")


async def main() -> None:
    probe_empty_archive()
    await probe_client()


if __name__ == "__main__":
    asyncio.run(main())

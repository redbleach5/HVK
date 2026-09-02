# -*- coding: utf-8 -*-
"""Длинное сообщение в чат: обрезка, промпт, стрим не падает."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.chat_limits import chat_message_max_chars, prepare_chat_message  # noqa: E402
from app.context.budget import fit_user_prompt, estimate_tokens  # noqa: E402

API = "http://127.0.0.1:8080"


def test_prepare() -> None:
    limit = chat_message_max_chars()
    huge = "а" * (limit + 10_000)
    clipped = prepare_chat_message(huge)
    assert len(clipped) <= limit + 80, len(clipped)
    assert "сокращён" in clipped
    print(f"prepare_chat_message ok limit={limit} clipped={len(clipped)}")


def test_fit_prompt() -> None:
    marker = "Сообщение автора:\n"
    body = "б" * 120_000
    user = f"КОНТЕКСТ\n\n{marker}{body}"
    fitted = fit_user_prompt(user, max_tokens=6000)
    assert marker in fitted
    assert estimate_tokens(fitted) < estimate_tokens(user)
    assert len(fitted) < len(user)
    print(f"fit_user_prompt ok {len(user)} -> {len(fitted)} chars")


async def test_api_stream() -> None:
    limit = chat_message_max_chars()
    payload = "в" * (limit + 5000)
    async with httpx.AsyncClient(base_url=API, timeout=httpx.Timeout(300.0, connect=10.0)) as client:
        health = await client.get("/health")
        health.raise_for_status()

        async with client.stream(
            "POST",
            "/chat/stream",
            data={"message": payload},
        ) as resp:
            assert resp.status_code == 200, resp.status_code
            got_done = False
            async for line in resp.aiter_lines():
                if '"t": "done"' in line or '"t":"done"' in line:
                    got_done = True
                    break
        assert got_done, "stream done missing"
    print("api stream large message ok")


def main() -> None:
    test_prepare()
    test_fit_prompt()
    asyncio.run(test_api_stream())
    print("VERIFY LARGE CHAT OK")


if __name__ == "__main__":
    main()

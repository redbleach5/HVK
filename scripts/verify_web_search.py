# -*- coding: utf-8 -*-
"""Инструменты поиска: схема, исполнение, живой ddgs."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.llm.tools import WEB_TOOLS, run_web_tool  # noqa: E402
from app.web.search import format_web_block, public_page_url, search_web  # noqa: E402


def test_schema() -> None:
    names = {item["function"]["name"] for item in WEB_TOOLS}
    if names != {"web_search", "fetch_page"}:
        raise SystemExit(f"unexpected tools: {names}")
    print("WEB_TOOLS ok")


def test_public_url() -> None:
    got = public_page_url("https://t.me/AshihminaDaria")
    if got != "https://t.me/s/AshihminaDaria":
        raise SystemExit(f"telegram preview {got}")
    print("public_page_url ok")


def test_format() -> None:
    block = format_web_block(
        [{"title": "Заголовок", "snippet": "Факт", "url": "https://example.com"}]
    )
    if "example.com" not in block:
        raise SystemExit("format_web_block missing url")
    if format_web_block([]):
        raise SystemExit("empty hits should be empty block")
    print("format_web_block ok")


async def test_live() -> None:
    text, hits = await run_web_tool("web_search", {"query": "погода Москва сегодня"})
    if not text:
        raise SystemExit("run_web_tool returned empty text")
    print(f"run_web_tool live ok hits={len(hits)} chars={len(text)}")
    empty, none = await run_web_tool("web_search", {"query": ""})
    if none:
        raise SystemExit("empty query should not hit")
    print("empty query ok", empty[:40])


def main() -> None:
    test_schema()
    test_public_url()
    test_format()
    asyncio.run(test_live())
    print("VERIFY WEB SEARCH OK")


if __name__ == "__main__":
    main()

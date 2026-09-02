"""Инструменты чата: поиск и чтение страниц. Модель вызывает сама."""

from __future__ import annotations

import logging
from typing import Any

from app.web.search import fetch_page, format_web_block, search_web

logger = logging.getLogger(__name__)

WEB_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the public web for current facts, news, people, blogs, "
                "Telegram channels. Use when the answer is not in the author's archive. "
                "Skip greetings and questions about her own posts."
            ),
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query in the user's language",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_page",
            "description": (
                "Open a URL and read public text. Use for http(s) links and t.me channels "
                "(public preview)."
            ),
            "parameters": {
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "http(s) or t.me URL",
                    }
                },
            },
        },
    },
]


def _args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    return {}


async def run_web_tool(name: str, arguments: Any) -> tuple[str, list[dict[str, str]]]:
    """Исполняет web_search / fetch_page. Всегда возвращает текст для модели."""
    args = _args(arguments)
    if name == "web_search":
        query = str(args.get("query") or args.get("q") or "").strip()
        hits = await search_web(query)
        logger.info("tool web_search q=%r hits=%s", query[:80], len(hits))
        if not hits:
            return "Поиск ничего не вернул.", []
        return format_web_block(hits), hits
    if name == "fetch_page":
        url = str(args.get("url") or args.get("link") or "").strip()
        text = await fetch_page(url)
        logger.info("tool fetch_page url=%r chars=%s", url[:80], len(text))
        if text:
            hit = {"title": url, "snippet": text[:320], "url": url}
            return f"Страница {url}:\n{text}", [hit]
        hits = await search_web(url)
        if hits:
            return "Страница не открылась. Поиск по адресу:\n" + format_web_block(hits), hits
        return "Страница недоступна.", []
    return f"Неизвестный инструмент: {name}", []

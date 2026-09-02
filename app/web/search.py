"""Поиск и чтение страниц для инструментов чата."""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

logger = logging.getLogger(__name__)

_TAG = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>", re.I)
_WS = re.compile(r"\s+")
_TG = re.compile(r"(?:https?://)?t\.me/(?:s/)?([A-Za-z0-9_]+)", re.I)


async def search_web(query: str, *, max_results: int = 4) -> list[dict[str, str]]:
    """DuckDuckGo text search. Пустой список при ошибке — чат не падает."""
    text = (query or "").strip()
    if not text:
        return []

    def _run() -> list[dict[str, str]]:
        from ddgs import DDGS

        out: list[dict[str, str]] = []
        with DDGS(timeout=10) as ddgs:
            rows: list[dict] = []
            try:
                rows = list(ddgs.text(text, max_results=max_results, region="ru-ru"))
            except Exception:
                rows = []
            if not rows:
                try:
                    rows = list(ddgs.news(text, max_results=max_results, region="ru-ru"))
                except Exception:
                    rows = []
            for row in rows:
                href = (row.get("href") or row.get("url") or "").strip()
                out.append(
                    {
                        "title": (row.get("title") or "").strip(),
                        "snippet": (row.get("body") or "").strip(),
                        "url": href,
                    }
                )
        return out

    try:
        return await asyncio.wait_for(asyncio.to_thread(_run), timeout=12.0)
    except Exception as exc:
        logger.warning("web search failed q=%r: %s", text[:80], exc)
        return []


def public_page_url(url: str) -> str:
    """Публичный URL: t.me/name → превью канала t.me/s/name."""
    raw = (url or "").strip()
    match = _TG.search(raw)
    if match:
        return f"https://t.me/s/{match.group(1)}"
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw:
        return "https://" + raw.lstrip("/")
    return ""


async def fetch_page(url: str, *, max_chars: int = 4000) -> str:
    """Скачивает публичный текст страницы. Пустая строка при ошибке."""
    target = public_page_url(url)
    if not target:
        return ""
    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; QuietDesk/1.0)"},
        ) as client:
            response = await client.get(target)
            response.raise_for_status()
            html = response.text or ""
        text = _TAG.sub(" ", html)
        text = _WS.sub(" ", text).strip()
        return text[:max_chars]
    except Exception as exc:
        logger.warning("fetch_page failed %s: %s", target[:80], exc)
        return ""


def format_web_block(hits: list[dict[str, str]]) -> str:
    """Текст для модели: результаты поиска."""
    if not hits:
        return ""
    lines = ["Результаты поиска:"]
    for i, hit in enumerate(hits, 1):
        title = hit.get("title") or "результат"
        snippet = (hit.get("snippet") or "")[:320]
        url = hit.get("url") or ""
        tail = f" ({url})" if url else ""
        lines.append(f"{i}. {title}: {snippet}{tail}")
    return "\n".join(lines)


async def web_context_block(message: str, *, max_results: int = 4) -> str:
    """Совместимость: поиск по строке."""
    hits = await search_web(message, max_results=max_results)
    return format_web_block(hits)

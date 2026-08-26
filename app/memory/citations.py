"""Цитаты из архива автора — не выдуманные «похожие посты»."""

from __future__ import annotations

import re

from app.db.models import Post
from app.memory.themes import is_promotional

_WORD = re.compile(r"[а-яёa-z]{4,}", re.IGNORECASE)


def post_snippet(post: Post, max_len: int = 100) -> str:
    """Одна строка из текста поста, без переносов."""
    text = " ".join((post.text or "").split())
    if not text:
        return (post.theme or "").strip()
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "…"
    return text


def post_citation(post: Post, max_len: int = 90) -> str:
    """Цитата для блока «почему», с номером поста."""
    snippet = post_snippet(post, max_len)
    pid = getattr(post, "id", None) or "?"
    return f"пост #{pid}: «{snippet}»" if snippet else f"пост #{pid}"


def reader_notes(post: Post, *, n: int = 2, cap: int = 80) -> str:
    """Короткие реплики читателей, если они есть у поста."""
    comments = post.comments or []
    bits: list[str] = []
    for raw in comments[:n]:
        if isinstance(raw, dict):
            text = str(raw.get("text") or raw.get("message") or "").strip()
        else:
            text = str(raw).strip()
        if text:
            bits.append(text[:cap])
    if not bits:
        return ""
    return "читатели: " + "; ".join(bits)


def digest_cites_posts(digest: str, posts: list[Post]) -> bool:
    """Проверяет, что сводка опирается на реальные слова из архива."""
    blob = (digest or "").lower()
    if not blob or not posts:
        return False
    for post in posts:
        words = _WORD.findall((post.text or "").lower())
        hits = sum(1 for word in words[:16] if word in blob)
        if hits >= 2:
            return True
    return False


def digest_from_posts(posts: list[Post]) -> tuple[str, list[dict[str, str]]]:
    """Сводка из её текстов — без модели, без выдумки и без рекламы со стены."""
    bits: list[str] = []
    for post in posts:
        text = (post.text or "").strip()
        if not text or is_promotional(text):
            continue
        bits.append(post_snippet(post, 110))
        if len(bits) >= 4:
            break
    if not bits:
        return "", []
    body = "Из твоих текстов: " + " · ".join(bits)
    return body, [{"text": bit} for bit in bits]

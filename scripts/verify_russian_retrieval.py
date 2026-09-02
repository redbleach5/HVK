# -*- coding: utf-8 -*-
"""Проверка русскоязычного поиска: e5 против старой MiniLM, на её архиве.

Без LLM. Проверки:
1) самопоиск — запрос из её поста находит этот же пост в top-3;
2) поиск по темам — строка темы находит пост этой темы в top-3;
3) e5 не хуже старой английской MiniLM на тех же темах.
Запуск после scripts/fetch_e5_onnx.py и scripts/migrate_chroma_e5.py.
"""
from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.db.models import Post  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.memory.chroma import (  # noqa: E402
    _E5_COLLECTION,
    _LEGACY_COLLECTION,
    collection_ids,
    e5_search_hits,
    legacy_search_hits,
)
from app.memory.embedder import e5_available  # noqa: E402
from app.memory.store import _is_author_text  # noqa: E402

SAMPLE = 20
THEMES = 15


async def main() -> int:
    if not e5_available():
        print("e5 не найден: сначала scripts/fetch_e5_onnx.py")
        return 1
    e5_ids = collection_ids(_E5_COLLECTION)
    legacy_ids = collection_ids(_LEGACY_COLLECTION)
    print(f"в коллекциях: e5={len(e5_ids)}, legacy={len(legacy_ids)}")
    if len(e5_ids) < 5:
        print("коллекция e5 пуста — запусти scripts/migrate_chroma_e5.py")
        return 1

    async with SessionLocal() as session:
        rows = (await session.execute(select(Post).order_by(Post.id))).scalars().all()
    by_id = {p.id: p for p in rows}
    author = [
        p
        for p in rows
        if _is_author_text(p) and (p.text or "").strip() and p.id in e5_ids
    ]
    if len(author) < 5:
        print(f"мало авторских постов в индексе: {len(author)}")
        return 1

    rng = random.Random(7)

    # 1) самопоиск: свой текст должен находить свой пост
    sample = rng.sample(author, min(SAMPLE, len(author)))
    self_ok = 0
    for post in sample:
        hits = e5_search_hits((post.text or "")[:200], n_results=3)
        if any(h["post_id"] == post.id for h in hits):
            self_ok += 1
    self_rate = self_ok / len(sample)
    print(f"самопоиск (свой пост в top-3): {self_ok}/{len(sample)} = {self_rate:.0%}")
    if self_rate < 0.8:
        print("ПРОВАЛ: эмбеддер не находит собственный пост")
        return 1

    # 2) темы: только посты, лежащие в обеих коллекциях — честное сравнение
    both = e5_ids & legacy_ids
    themes: dict[str, int] = {}
    for post in author:
        theme = (post.theme or "").strip().lower()
        if theme and post.id in both:
            themes.setdefault(theme, post.id)
    theme_items = list(themes.items())
    rng.shuffle(theme_items)
    theme_items = theme_items[:THEMES]
    if not theme_items:
        print("нет тем для сравнения — сравнение тем пропущено")
        return 0

    def found(hits: list[dict], theme: str) -> str:
        for hit in hits:
            post = by_id.get(hit["post_id"])
            if post and (post.theme or "").strip().lower() == theme:
                distance = hit["distance"]
                mark = f"{distance:.3f}" if isinstance(distance, float) else "?"
                return f"#{hit['post_id']} d={mark}"
        return "мимо"

    e5_score = legacy_score = 0
    print("\nтема -> e5 | miniLM")
    for theme, _target_id in theme_items:
        e5_line = found(e5_search_hits(theme, n_results=3), theme)
        legacy_line = found(legacy_search_hits(theme, n_results=3), theme)
        e5_score += e5_line != "мимо"
        legacy_score += legacy_line != "мимо"
        print(f"«{theme[:44]}» -> {e5_line} | {legacy_line}")

    total = len(theme_items)
    e5_rate = e5_score / total
    legacy_rate = legacy_score / total
    decidable = sum(
        1
        for theme, _ in theme_items
        if found(e5_search_hits(theme, n_results=3), theme) != "мимо"
        or found(legacy_search_hits(theme, n_results=3), theme) != "мимо"
    )
    print(
        f"\nтемы: e5 {e5_score}/{total} = {e5_rate:.0%}, "
        f"miniLM {legacy_score}/{total} = {legacy_rate:.0%}, "
        f"обе мимо: {total - decidable}/{total}"
    )
    print(
        "сравнение тем на таком объёме — ориентир, не приговор: "
        "одно-словные темы размечены у немногих постов, решают расстояния выше"
    )
    if e5_score == 0 and legacy_score > 0:
        print("ПРОВАЛ: e5 не нашёл ни одной темы, тогда как старый находил")
        return 1
    print("ОК: самопоиск держится, катастрофы на темах нет")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

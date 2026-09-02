# -*- coding: utf-8 -*-
"""Словесный слой поиска переживает падежи.

Без LLM. Две части:
1) ключи основ: «чаю»=«чай», «дочку»=«дочь», «осенью»=«осенний» и т.д.;
2) на реальном архиве: запрос с искусственно изменённым окончанием
   находит тот же пост через словесный слой (векторный слой отключён).
   Для честности печатаем, сколько бы нашёл старый точный матч.
"""
from __future__ import annotations

import asyncio
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import desc, select  # noqa: E402

import app.memory.retrieve as retrieve  # noqa: E402
from app.db.models import Post  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.memory.retrieve import (  # noqa: E402
    _STOP_KEYS,
    _key,
    _keys,
    posts_for_query,
)
from app.memory.store import _is_author_text  # noqa: E402

SAMPLE = 15
_WORD = re.compile(r"[а-яё]{5,}")

PAIRS = [
    ("чаю", "чай"),
    ("чаи", "чай"),
    ("дочку", "дочь"),
    ("дочке", "дочка"),
    ("осенью", "осенний"),
    ("осеннюю", "осенний"),
    ("рецепты", "рецепт"),
    ("рецептом", "рецепт"),
    ("гардеробе", "гардероб"),
    ("гардероба", "гардероб"),
    ("мамина", "мамин"),
    ("соли", "соль"),
    ("дома", "дом"),
    ("чайника", "чайник"),
]


def _case_check() -> int:
    bad = [(a, b, _key(a), _key(b)) for a, b in PAIRS if _key(a) != _key(b)]
    if bad:
        for a, b, ka, kb in bad:
            print(f"ПРОВАЛ: «{a}» -> {ka!r}, «{b}» -> {kb!r}")
        return 1
    print(f"ключи основ: все {len(PAIRS)} пар сошлись")
    return 0


def _inflect(word: str) -> str:
    """Имитация падежа: меняем/добавляем гласный хвост."""
    if word[-1] in "аяоёеуюыи":
        return word + "м"
    return word + "а"


async def main() -> int:
    if _case_check():
        return 1

    # Изолируем словесный слой: векторный поиск вертим в пустоту.
    retrieve.search_posts = lambda *args, **kwargs: []  # type: ignore[assignment]

    async with SessionLocal() as session:
        result = await session.execute(
            select(Post).order_by(desc(Post.engagement), desc(Post.id)).limit(120)
        )
        pool = [p for p in result.scalars() if _is_author_text(p)]
        rng = random.Random(11)
        sample = rng.sample(pool, min(SAMPLE, len(pool)))
        new_hits = old_hits = checked = 0
        misses: list[str] = []
        for post in sample:
            words = list(dict.fromkeys(_WORD.findall((post.text or "").lower())))
            good: list[tuple[str, str]] = []
            for w in words:
                inflected_w = _inflect(w)
                key_w = _key(inflected_w)
                if not key_w or key_w in retrieve._STOP_KEYS:
                    continue
                # Редкое содержательное слово: иначе меряем порядок по
                # вовлечению среди релевантных, а не морфологию.
                sharers = sum(1 for q in pool if key_w in _keys(q.text or ""))
                if sharers <= 3:
                    good.append((w, inflected_w))
            if not good:
                continue
            word, inflected = rng.choice(good)
            # Запрос из одного слова: изолируем морфологию, не разбавляя
            # сигнал общими словами — их вклад проверяет стоп-лист отдельно.
            query = inflected
            found = await posts_for_query(session, query, limit=10)
            checked += 1
            if any(p.id == post.id for p in found):
                new_hits += 1
            else:
                misses.append(
                    f"«{inflected}» -> ждали #{post.id}, "
                    f"получили {[p.id for p in found[:5]]}"
                )
            if inflected in (post.text or "").lower():
                old_hits += 1
    if checked == 0:
        print("нет подходящих постов для проверки")
        return 1
    rate = new_hits / checked
    print(
        f"падежи в словесном слое: {new_hits}/{checked} = {rate:.0%}; "
        f"старый точный матч поймал бы {old_hits}/{checked}"
    )
    for miss in misses:
        print(f"  промах: {miss}")
    if rate < 0.8:
        print("ПРОВАЛ: словесный слой слишком чувствителен к окончаниям")
        return 1
    print("ОК: словесный слой держит падежи")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

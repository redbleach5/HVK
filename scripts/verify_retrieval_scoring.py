# -*- coding: utf-8 -*-
"""Качество фьюжн-поиска (e5 + ключи) на её архиве. Без LLM.

Закрепляет калибровку весов (см. scripts/_probe_retrieval_weights.py):
семантика должна доминировать над случайным ключом, но ключи живы
как запасной слой. Проверки:
1. самопоиск@3 ≥ 0.9 (запрос из поста возвращает пост в top-3);
2. семантические соседи e5 (top-3) удерживаются фьюжном ≥ 0.40;
3. ключевой слой изолированно (семантика off) находит свой пост
   по редкому слову ≥ 0.8;
4. на проектном вопросе результат содержит её темы (гардероб/рецепт/доч).
"""
from __future__ import annotations

import asyncio
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import desc, select  # noqa: E402

import app.memory.retrieve as retrieve  # noqa: E402
from app.db.models import Post  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.memory.retrieve import _keys, posts_for_query  # noqa: E402
from app.memory.store import _is_author_text  # noqa: E402

SAMPLE = 15
QUESTION = (
    "Кажется, я уже писала про осенний гардероб и мамин рецепт. "
    "Что лучше выложить в сообщество сейчас, чтобы не повторяться?"
)
THEMES = ("гардероб", "рецепт", "доч")
_WORD = re.compile(r"[а-яё]{5,}")


async def main() -> int:
    real_search = retrieve.search_posts
    problems: list[str] = []
    async with SessionLocal() as session:
        rows = (
            (await session.execute(select(Post).order_by(desc(Post.id)))).scalars().all()
        )
        pool = [p for p in rows if _is_author_text(p) and (p.text or "").strip()]
        rng = random.Random(31)
        sample = rng.sample(pool, min(SAMPLE, len(pool)))

        # 1+2) самопоиск и сохранение семантики (полный фьюжн)
        self_hits = 0
        preserve = 0
        for post in sample:
            q = " ".join((post.text or "").split())[:140]
            semantic = await asyncio.to_thread(real_search, q, 6)
            sem3 = {int(h["post_id"]) for h in semantic[:3]}
            found = await posts_for_query(session, q, limit=6)
            found_ids = [p.id for p in found[:3]]
            if post.id in found_ids:
                self_hits += 1
            preserve += len(sem3 & set(found_ids))
        self_rate = self_hits / len(sample)
        preserve_rate = preserve / (3 * len(sample))
        print(
            f"самопоиск@3: {self_hits}/{len(sample)} = {self_rate:.0%}; "
            f"e5-top3 в фьюжне: {preserve}/{3 * len(sample)} = {preserve_rate:.0%}"
        )
        if self_rate < 0.9:
            problems.append(f"самопоиск@{len(sample)}≥0.9 не достигнут: {self_rate:.0%}")
        if preserve_rate < 0.40:
            problems.append(
                f"семантические соседи вытесняются ключами: {preserve_rate:.0%}"
            )

        # 3) ключевой слой изолированно (семантика off)
        retrieve.search_posts = lambda *args, **kwargs: []  # type: ignore[assignment]
        key_hits = 0
        key_checked = 0
        for post in sample:
            words = list(dict.fromkeys(_WORD.findall((post.text or "").lower())))
            good: list[str] = []
            for w in words:
                key_w = retrieve._key(w)
                if not key_w or key_w in retrieve._STOP_KEYS:
                    continue
                sharers = sum(1 for qq in pool if key_w in _keys(qq.text or ""))
                if sharers <= 3:
                    good.append(w)
            if not good:
                continue
            word = rng.choice(good)
            found = await posts_for_query(session, word, limit=6)
            key_checked += 1
            if any(p.id == post.id for p in found):
                key_hits += 1
        retrieve.search_posts = real_search
        key_rate = key_hits / max(key_checked, 1)
        print(
            f"ключевой слой (редкое слово, семантика off): "
            f"{key_hits}/{key_checked} = {key_rate:.0%}"
        )
        if key_rate < 0.8:
            problems.append(f"ключевой слой ослаб: {key_rate:.0%}")

        # 4) проектный вопрос — темы на месте (полный фьюжн)
        found_q = await posts_for_query(session, QUESTION, limit=6)
        blob = " ".join((p.text or "") for p in found_q).lower()
        missed = [t for t in THEMES if t not in blob]
        print(f"проектный вопрос: темы {[t for t in THEMES if t in blob] or 'не найдены'}")
        if missed:
            problems.append(f"проектный вопрос не вернул темы: {missed}")

    if problems:
        print("\nПРОВАЛ:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nОК: поиск качественный (семантика держится, ключи живы)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
# -*- coding: utf-8 -*-
"""Калибровка весов слоёв поиска (семантика vs ключи) на её архиве.

Метрика качества — самопоиск@3: запрос из начала поста должен возвращать
этот же пост в top-3 через полный фьюжн (e5 + ключи). Смотрим, какая
комбинация весов даёт максимум при сохранении ключевой достижимости.
"""
from __future__ import annotations

import asyncio
import random
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
COMBOS = [
    (4.0, 8.0),  # прежние веса (базовая линия)
    (5.0, 3.5),
    (5.0, 2.5),
    (5.5, 3.0),
    (6.0, 3.0),
    (6.5, 2.0),  # семантически плотнее: e5 доминирует
    (7.0, 1.5),  # семантика ключевая, ключ — подсказка
    (7.0, 1.0),  # максимальный вес семантике
    (5.5, 1.0),  # балансировка: умеренно
]


async def main() -> int:
    async with SessionLocal() as session:
        rows = (
            (await session.execute(select(Post).order_by(desc(Post.id)))).scalars().all()
        )
        pool = [p for p in rows if _is_author_text(p) and (p.text or "").strip()]
        rng = random.Random(21)
        sample = rng.sample(pool, min(SAMPLE, len(pool)))

        for sem, key in COMBOS:
            retrieve._SEM_MULT = sem
            retrieve._KEY_WEIGHT = key
            self_hits = 0
            preserve = 0
            far_leak = 0
            for post in sample:
                q = " ".join((post.text or "").split())[:140]
                # семантические соседи запроса по e5 (эталон качества)
                semantic = await asyncio.to_thread(retrieve.search_posts, q, 12)
                sem_ids = [int(h["post_id"]) for h in semantic]
                sem3 = set(sem_ids[:3])
                sem_far = set(sem_ids[4:10])
                found = await posts_for_query(session, q, limit=6)
                found_ids = [p.id for p in found[:3]]
                if post.id in found_ids:
                    self_hits += 1
                preserve += len(sem3 & set(found_ids))
                far_leak += len(sem_far & set(found_ids))
            print(
                f"sem×{sem:<4} key×{key:<4} -> самопоиск@3 {self_hits}/{len(sample)}; "
                f"e5-top3 в фьюжне {preserve}/{3 * len(sample)} "
                f"({preserve / (3 * len(sample)):.0%}); "
                f"дальних утечек в top-3: {far_leak}/{3 * len(sample)}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
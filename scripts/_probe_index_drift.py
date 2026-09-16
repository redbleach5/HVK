# -*- coding: utf-8 -*-
"""Индекс и архив: все ли авторские посты проиндексированы.

Запуск: C:\\HVK\\.venv\\Scripts\\python.exe scripts\\_probe_index_drift.py

Сравнивает число авторских постов в SQLite с числом постов в Chroma.
Если индекс отстал (например, после импорта стены), это увидит idle-задача
reindex_archive — или можно догнать вручную.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.memory.chroma import get_chroma  # noqa: E402
from app.memory.store import MemoryStore  # noqa: E402


async def main() -> int:
    async with SessionLocal() as session:
        author_n = await MemoryStore(session).count_author_posts()
    collection = get_chroma()
    rows = collection.get(include=["metadatas"])
    metas = rows.get("metadatas") or []
    post_ids = sorted({int(m.get("post_id")) for m in metas if m.get("post_id")})
    chunks = len(metas)
    print(f"авторских постов в БД: {author_n}")
    print(f"кусков в индексе: {chunks}, уникальных постов: {len(post_ids)}")
    missing = author_n - len(post_ids)
    if missing > 0:
        print(f"ОТСТАВАНИЕ: {missing} постов без вектора (догонит idle reindex_archive)")
        return 1
    print("ОК: индекс не отстаёт")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
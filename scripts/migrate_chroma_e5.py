# -*- coding: utf-8 -*-
"""Переиндексация архива в русскоязычную коллекцию Chroma (e5).

Запускать один раз после scripts/fetch_e5_onnx.py.
Старая коллекция не трогается: откат — удалить папку data/models/e5-small-onnx,
и проект вернётся к прежнему поиску без потери данных.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.memory.chroma import get_chroma  # noqa: E402
from app.memory.embedder import e5_available, get_embedder  # noqa: E402
from app.memory.ingest import reindex_posts  # noqa: E402


async def main() -> int:
    if not e5_available():
        print("модель не найдена: сначала scripts/fetch_e5_onnx.py")
        return 1
    # Прогрев: один вектор, чтобы упасть сразу, а не на двухсотом посте.
    probe = get_embedder().embed(["query: проверка"], query=True)
    if not probe or not probe[0]:
        print("эмбеддер вернул пустой вектор")
        return 1
    print(f"эмбеддер ок, размерность {len(probe[0])}")
    collection = get_chroma()
    print(f"коллекция: {collection.name}, в ней {collection.count()} постов")
    async with SessionLocal() as session:
        count = await reindex_posts(session)
        await session.commit()
    print(f"переиндексировано: {count}; в коллекции стало {get_chroma().count()}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

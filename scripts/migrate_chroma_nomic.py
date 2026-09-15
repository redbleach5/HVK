# -*- coding: utf-8 -*-
"""Переиндексация архива в коллекцию author_posts_nomic (эмбеддер Ollama).

Запускать один раз: nomic-embed-text-v2-moe уже скачан в Ollama.
Длинные посты кладутся кусками (700 симв., перекрытие 100), поиск
дедуплицируется по посту. Старые коллекции (e5, legacy) не трогаются:
откат — выключить Ollama/удалить модель, и проект вернётся на e5.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.memory.chroma import (
    _NOMIC_COLLECTION,
    _get_client,
    get_chroma,
)  # noqa: E402
from app.memory.embedder import active_mode, get_embedder_any  # noqa: E402
from app.memory.ingest import reindex_posts  # noqa: E402


async def main() -> int:
    if active_mode() != "ollama-nomic":
        print("эмбеддер Ollama недоступен: запусти Ollama и проверь модель")
        print(f"  (ожидается {get_settings().embedding_ollama_model})")
        return 1
    # Прогрев: один вектор, чтобы упасть сразу, а не на двухсотом посте.
    probe = get_embedder_any().embed(["проверка связи"], query=True)
    if not probe or not probe[0]:
        print("эмбеддер вернул пустой вектор")
        return 1
    print(f"эмбеддер ок, размерность {len(probe[0])}")
    # Чистый старт: старые куски не должны смешаться с новыми.
    try:
        _get_client().delete_collection(_NOMIC_COLLECTION)
        print(f"коллекция {_NOMIC_COLLECTION} очищена")
    except Exception:
        print(f"коллекция {_NOMIC_COLLECTION} ещё не существовала")
    collection = get_chroma()
    print(f"коллекция: {collection.name}")
    async with SessionLocal() as session:
        count = await reindex_posts(session)
        await session.commit()
    total = get_chroma().count()
    print(f"переиндексировано постов: {count}; кусков в коллекции стало {total}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

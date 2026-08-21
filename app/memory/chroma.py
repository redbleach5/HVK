"""Векторный архив постов на ChromaDB."""

from __future__ import annotations

import logging
from typing import Any, Optional

import chromadb
from chromadb.utils import embedding_functions

from app.config import get_settings

logger = logging.getLogger(__name__)

_COLLECTION = "author_posts"

_client: chromadb.PersistentClient | None = None
_embedder = None


def _get_embedder():
    """Локальный ONNX-эмбеддер Chroma. Без облака, один способ на весь проект."""
    global _embedder
    if _embedder is None:
        _embedder = embedding_functions.DefaultEmbeddingFunction()
    return _embedder


def get_chroma() -> chromadb.Collection:
    """Возвращает коллекцию архива постов."""
    global _client
    settings = get_settings()
    path = str(settings.resolve_path(settings.chroma_path))
    if _client is None:
        _client = chromadb.PersistentClient(path=path)
    return _client.get_or_create_collection(
        name=_COLLECTION,
        embedding_function=_get_embedder(),
        metadata={"hnsw:space": "cosine"},
    )


def upsert_post(
    post_id: int,
    text: str,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Кладёт или обновляет пост в векторном индексе."""
    if not text.strip():
        return
    collection = get_chroma()
    meta = {k: v for k, v in (metadata or {}).items() if v is not None}
    meta["post_id"] = post_id
    collection.upsert(
        ids=[str(post_id)],
        documents=[text[:8000]],
        metadatas=[meta],
    )


def search_posts(query: str, n_results: int = 5) -> list[dict[str, Any]]:
    """Ищет похожие посты по смыслу."""
    collection = get_chroma()
    if collection.count() == 0:
        return []
    result = collection.query(
        query_texts=[query],
        n_results=min(n_results, max(collection.count(), 1)),
        include=["documents", "metadatas", "distances"],
    )
    hits: list[dict[str, Any]] = []
    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    for i, doc_id in enumerate(ids):
        hits.append(
            {
                "post_id": int(metas[i].get("post_id") or doc_id),
                "text": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
                "distance": dists[i] if i < len(dists) else None,
            }
        )
    return hits


def similar_to_post(post_id: int, n_results: int = 5) -> list[dict[str, Any]]:
    """Ищет посты, похожие на уже известный."""
    collection = get_chroma()
    try:
        got = collection.get(ids=[str(post_id)], include=["documents"])
    except Exception:
        return []
    docs = got.get("documents") or []
    if not docs or not docs[0]:
        return []
    hits = search_posts(docs[0], n_results=n_results + 1)
    return [h for h in hits if h["post_id"] != post_id][:n_results]

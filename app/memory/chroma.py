"""Векторный архив постов на ChromaDB.

Эмбеддинги — локальный русскоязычный e5 (app/memory/embedder.py): вектора
считаем сами и передаём явно. Файлов модели нет — работаем по-старому,
дефолтной английской MiniLM на коллекции author_posts. Облака нет ни так, ни так.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import chromadb
from chromadb.utils import embedding_functions

from app.config import get_settings
from app.memory.themes import is_promotional

logger = logging.getLogger(__name__)

_LEGACY_COLLECTION = "author_posts"  # старая английская MiniLM
_E5_COLLECTION = "author_posts_e5"  # русскоязычная замена

_client: chromadb.PersistentClient | None = None
_collections: dict[str, chromadb.Collection] = {}
_embedder = None


def _get_embedder():
    """Старый ONNX-эмбеддер Chroma — только для legacy-коллекции."""
    global _embedder
    if _embedder is None:
        _embedder = embedding_functions.DefaultEmbeddingFunction()
    return _embedder


def _e5_mode() -> bool:
    from app.memory.embedder import e5_available

    return e5_available()


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        settings = get_settings()
        path = str(settings.resolve_path(settings.chroma_path))
        _client = chromadb.PersistentClient(path=path)
    return _client


def get_chroma() -> chromadb.Collection:
    """Активная коллекция архива: e5, если модель на месте, иначе legacy."""
    name = _E5_COLLECTION if _e5_mode() else _LEGACY_COLLECTION
    cached = _collections.get(name)
    if cached is not None:
        return cached
    if _e5_mode():
        # Вектора считаем сами — дефолтная английская MiniLM не нужна.
        col = _get_client().get_or_create_collection(
            name=name, metadata={"hnsw:space": "cosine"}
        )
    else:
        col = _get_client().get_or_create_collection(
            name=name,
            embedding_function=_get_embedder(),
            metadata={"hnsw:space": "cosine"},
        )
    _collections[name] = col
    return col


def _embed_texts(texts: list[str], *, query: bool) -> Optional[list[list[float]]]:
    """Вектора e5 или None, если посчитать не удалось."""
    if not _e5_mode():
        return None
    try:
        from app.memory.embedder import get_embedder

        return get_embedder().embed(texts, query=query)
    except Exception:
        logger.exception("e5-эмбеддинг не посчитался")
        return None


def upsert_post(
    post_id: int,
    text: str,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Кладёт или обновляет пост в векторном индексе."""
    if not text.strip() or is_promotional(text):
        return
    collection = get_chroma()
    meta = {k: v for k, v in (metadata or {}).items() if v is not None}
    meta["post_id"] = post_id
    doc = text[:8000]
    if _e5_mode():
        vectors = _embed_texts([doc], query=False)
        if vectors is None:
            # Чужой вектор в e5-коллекцию не пишем — idle-воркер доиндексирует.
            logger.warning("upsert_post: пост %s без вектора — пропущен", post_id)
            return
        collection.upsert(
            ids=[str(post_id)], embeddings=vectors, documents=[doc], metadatas=[meta]
        )
        return
    collection.upsert(ids=[str(post_id)], documents=[doc], metadatas=[meta])


def _parse_query_result(
    result: dict[str, Any], *, with_docs: bool
) -> list[dict[str, Any]]:
    """Единый разбор ответа collection.query."""
    hits: list[dict[str, Any]] = []
    ids = (result.get("ids") or [[]])[0]
    docs = (result.get("documents") or [[]])[0] if with_docs else []
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    for i, doc_id in enumerate(ids):
        meta = metas[i] if i < len(metas) else {}
        hits.append(
            {
                "post_id": int(meta.get("post_id") or doc_id),
                "text": docs[i] if with_docs and i < len(docs) else "",
                "metadata": meta if meta else {},
                "distance": dists[i] if i < len(dists) else None,
            }
        )
    return hits


def search_posts(
    query: str, n_results: int = 5, *, as_query: bool = True
) -> list[dict[str, Any]]:
    """Ищет похожие посты по смыслу. as_query=False — пост к посту."""
    collection = get_chroma()
    count = max(collection.count(), 1)
    if collection.count() == 0:
        return []
    if _e5_mode():
        vectors = _embed_texts([query], query=as_query)
        if vectors is None:
            return []
        result = collection.query(
            query_embeddings=vectors,
            n_results=min(n_results, count),
            include=["documents", "metadatas", "distances"],
        )
    else:
        result = collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
            include=["documents", "metadatas", "distances"],
        )
    return _parse_query_result(result, with_docs=True)


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
    hits = search_posts(docs[0], n_results=n_results + 1, as_query=False)
    return [h for h in hits if h["post_id"] != post_id][:n_results]


def collection_ids(name: str) -> set[int]:
    """Все post_id в named-коллекции. Для проверок, без эмбеддера."""
    if name == _LEGACY_COLLECTION:
        col = _get_client().get_or_create_collection(
            name=name,
            embedding_function=_get_embedder(),
            metadata={"hnsw:space": "cosine"},
        )
    else:
        col = _get_client().get_or_create_collection(
            name=name, metadata={"hnsw:space": "cosine"}
        )
    raw = (col.get(include=[]) or {}).get("ids") or []
    return {int(x) for x in raw}


def e5_search_hits(query: str, n_results: int = 6) -> list[dict[str, Any]]:
    """Хиты (post_id, distance) из новой коллекции. Для verify-скриптов."""
    col = _get_client().get_or_create_collection(
        name=_E5_COLLECTION, metadata={"hnsw:space": "cosine"}
    )
    if col.count() == 0:
        return []
    vectors = _embed_texts([query], query=True)
    if vectors is None:
        return []
    result = col.query(
        query_embeddings=vectors,
        n_results=min(n_results, col.count()),
        include=["metadatas", "distances"],
    )
    return _parse_query_result(result, with_docs=False)


def legacy_search_hits(query: str, n_results: int = 6) -> list[dict[str, Any]]:
    """Хиты из старой коллекции MiniLM. Только для сравнения в verify-скриптах."""
    col = _get_client().get_or_create_collection(
        name=_LEGACY_COLLECTION,
        embedding_function=_get_embedder(),
        metadata={"hnsw:space": "cosine"},
    )
    if col.count() == 0:
        return []
    result = col.query(
        query_texts=[query],
        n_results=min(n_results, col.count()),
        include=["metadatas", "distances"],
    )
    return _parse_query_result(result, with_docs=False)

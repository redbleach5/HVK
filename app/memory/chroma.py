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
_E5_COLLECTION = "author_posts_e5"  # русскоязычная e5-small (onnx)
_NOMIC_COLLECTION = "author_posts_nomic"  # русскоязычный MoE-эмбеддер Ollama

# Длинный пост одним вектором «размывается»: запрос из его начала (140 симв.)
# находит чужие короткие посты ближе, чем его же тело (см.
# scripts/_probe_selfsearch_fail.py: пост #26 вообще выпадал из топ-10).
# Поэтому длинные тексты режем на перекрывающиеся куски; поиск отвечает
# постами (дедуп по post_id, лучший кусок).
_CHUNK_SIZE = 700
_CHUNK_OVERLAP = 100
_SINGLE_DOC_MAX = 900

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


def _semantic_mode() -> Optional[str]:
    """'ollama-nomic' | 'e5' | None — согласован с выбором эмбеддера."""
    from app.memory.embedder import active_mode

    return active_mode()


def _collection_name() -> str:
    mode = _semantic_mode()
    if mode == "ollama-nomic":
        return _NOMIC_COLLECTION
    if mode == "e5":
        return _E5_COLLECTION
    return _LEGACY_COLLECTION


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        settings = get_settings()
        path = str(settings.resolve_path(settings.chroma_path))
        _client = chromadb.PersistentClient(path=path)
    return _client


def get_chroma() -> chromadb.Collection:
    """Активная коллекция архива: nomic, если Ollama с ним жива; иначе e5; иначе legacy."""
    name = _collection_name()
    cached = _collections.get(name)
    if cached is not None:
        return cached
    if _semantic_mode() is not None:
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
    """Вектора активного семантического слоя или None, если не посчитались."""
    if _semantic_mode() is None:
        return None
    try:
        from app.memory.embedder import get_embedder_any

        return get_embedder_any().embed(texts, query=query)
    except Exception:
        logger.exception("эмбеддинг не посчитался")
        return None


def _chunks(text: str) -> list[str]:
    """Куски поста: до 900 символов целиком, длинный — с перекрытием."""
    body = text.strip()
    if len(body) <= _SINGLE_DOC_MAX:
        return [body]
    step = _CHUNK_SIZE - _CHUNK_OVERLAP
    chunks: list[str] = []
    for start in range(0, len(body), step):
        piece = body[start : start + _CHUNK_SIZE].strip()
        if piece:
            chunks.append(piece)
        if start + _CHUNK_SIZE >= len(body):
            break
    return chunks or [body]


def _delete_post_chunks(collection: chromadb.Collection, post_id: int) -> None:
    """Старые куски поста уходят целиком, чтобы не остался протухший вектор."""
    try:
        collection.delete(where={"post_id": post_id})
    except Exception:
        logger.exception("не удалось удалить старые куски поста %s", post_id)


def upsert_post(
    post_id: int,
    text: str,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Кладёт или обновляет пост в векторном индексе (длинные — кусками)."""
    if not text.strip() or is_promotional(text):
        return
    collection = get_chroma()
    meta = {k: v for k, v in (metadata or {}).items() if v is not None}
    meta["post_id"] = post_id
    parts = _chunks(text[:8000])
    if _semantic_mode() is not None:
        vectors = _embed_texts(parts, query=False)
        if vectors is None:
            # Чужой вектор в коллекцию не пишем — idle-воркер доиндексирует.
            logger.warning("upsert_post: пост %s без вектора — пропущен", post_id)
            return
        _delete_post_chunks(collection, post_id)
        if len(parts) == 1:
            collection.upsert(
                ids=[str(post_id)],
                embeddings=[vectors[0]],
                documents=[parts[0]],
                metadatas=[meta],
            )
            return
        collection.upsert(
            ids=[f"{post_id}#{i}" for i in range(len(parts))],
            embeddings=vectors,
            documents=parts,
            metadatas=[dict(meta, chunk=i) for i in range(len(parts))],
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
    """Ищет похожие посты по смыслу. as_query=False — пост к посту.

    Коллекция может хранить пост кусками (длинные тексты), поэтому
    выдача дедуплицируется по post_id — один пост, лучший его кусок.
    """
    collection = get_chroma()
    count = max(collection.count(), 1)
    if collection.count() == 0:
        return []
    if _semantic_mode() is not None:
        vectors = _embed_texts([query], query=as_query)
        if vectors is None:
            return []
        # Запас на куски одного поста: после дедупа должно остаться n_results.
        fetch = min(count, max(n_results * 3, n_results + 6))
        result = collection.query(
            query_embeddings=vectors,
            n_results=fetch,
            include=["documents", "metadatas", "distances"],
        )
    else:
        result = collection.query(
            query_texts=[query],
            n_results=min(n_results, count),
            include=["documents", "metadatas", "distances"],
        )
    hits = _parse_query_result(result, with_docs=True)
    best: dict[int, dict[str, Any]] = {}
    for hit in hits:
        pid = int(hit["post_id"])
        prev = best.get(pid)
        dist = hit.get("distance")
        prev_dist = prev.get("distance") if prev else None
        if prev is None or (dist is not None and (prev_dist is None or dist < prev_dist)):
            best[pid] = hit
    merged = sorted(
        best.values(),
        key=lambda h: (h.get("distance") is None, h.get("distance") or 0.0),
    )
    return merged[:n_results]


def similar_to_post(post_id: int, n_results: int = 5) -> list[dict[str, Any]]:
    """Ищет посты, похожие на уже известный."""
    collection = get_chroma()
    try:
        got = collection.get(where={"post_id": post_id}, include=["documents"])
        docs = got.get("documents") or []
        if not docs:
            got = collection.get(ids=[str(post_id)], include=["documents"])
            docs = got.get("documents") or []
    except Exception:
        return []
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
    # Куски одного поста («26#0», «26#1») схлопываем в пост.
    return {int(str(x).split("#")[0]) for x in raw}


def e5_search_hits(query: str, n_results: int = 6) -> list[dict[str, Any]]:
    """Хиты (post_id, distance) из e5-коллекции. Для verify-скриптов.

    Всегда e5-эмбеддер: скрипт сравнивает именно e5 с legacy, даже если
    активный режим проекта переключён на nomic.
    """
    col = _get_client().get_or_create_collection(
        name=_E5_COLLECTION, metadata={"hnsw:space": "cosine"}
    )
    if col.count() == 0:
        return []
    try:
        from app.memory.embedder import get_embedder

        vectors = get_embedder().embed([query], query=True)
    except Exception:
        return []
    if not vectors:
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

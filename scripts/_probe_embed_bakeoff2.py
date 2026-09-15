# -*- coding: utf-8 -*-
"""Bake-off эмбеддеров на полном архиве: e5-small vs nomic-v2-moe (Ollama).

Самопоиск@1/@3 по всем постам (запрос = первые 140 симв.),
проектный вопрос — темы в top-3.
"""
from __future__ import annotations

import asyncio
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlalchemy import desc, select

from app.db.models import Post
from app.db.session import SessionLocal
from app.memory.embedder import get_embedder
from app.memory.store import _is_author_text

OLLAMA = "http://127.0.0.1:11434/api/embed"
NOMIC = "nomic-embed-text-v2-moe:latest"
QUESTION = (
    "Кажется, я уже писала про осенний гардероб и мамин рецепт. "
    "Что лучше выложить в сообщество сейчас, чтобы не повторяться?"
)
THEMES = ("гардероб", "рецепт", "доч")


def ollama_embed(texts: list[str], *, prefix: str | None) -> list[list[float]]:
    if prefix:
        texts = [prefix + t for t in texts]
    payload = {"model": NOMIC, "input": texts}
    req = urllib.request.Request(
        OLLAMA,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["embeddings"]


def _norm(m: np.ndarray) -> np.ndarray:
    return m / np.clip(np.linalg.norm(m, axis=1, keepdims=True), 1e-9, None)


def _stats(docs: np.ndarray, queries: np.ndarray, label: str) -> None:
    sims = queries @ docs.T
    n = len(queries)
    top1 = float((sims.argmax(axis=1) == np.arange(n)).mean())
    top3 = float(
        (np.argsort(-sims, axis=1)[:, :3] == np.arange(n)[:, None]).any(axis=1).mean()
    )
    mean_d = float(np.mean(np.diag(sims)))
    print(f"{label}: self@1={top1:.0%} self@3={top3:.0%} (cos средний {mean_d:.3f}, n={n})")


def _theme_blob(qvec: np.ndarray, docs: np.ndarray, pool) -> list[str]:
    sims = (qvec @ docs.T)[0]
    top3 = [pool[i] for i in np.argsort(-sims)[:3]]
    blob = " ".join((p.text or "") for p in top3).lower()
    return [t for t in THEMES if t in blob]


async def main() -> int:
    async with SessionLocal() as session:
        rows = (
            (await session.execute(select(Post).order_by(desc(Post.id)))).scalars().all()
        )
        pool = [p for p in rows if _is_author_text(p) and (p.text or "").strip()]
    docs_texts = [(p.text or "").strip()[:8000] for p in pool]
    queries = [" ".join((p.text or "").split())[:140] for p in pool]
    print(f"архив: {len(pool)} постов")

    emb = get_embedder()
    d_e5 = _norm(np.asarray(emb.embed(docs_texts, query=False), dtype=float))
    q_e5 = _norm(np.asarray(emb.embed(queries, query=True), dtype=float))
    t_e5 = _norm(np.asarray(emb.embed([QUESTION], query=True), dtype=float))
    print("== e5-small (текущий) ==")
    _stats(d_e5, q_e5, "self-search")
    print(f"проектный вопрос, темы: {_theme_blob(t_e5, d_e5, pool)}")

    for prefix_q, prefix_d, label in (
        (None, None, "nomic без префиксов"),
        ("search_query: ", "search_document: ", "nomic с search_-префиксами"),
    ):
        d = _norm(np.asarray(ollama_embed(docs_texts, prefix=prefix_d), dtype=float))
        q = _norm(np.asarray(ollama_embed(queries, prefix=prefix_q), dtype=float))
        t = _norm(np.asarray(ollama_embed([QUESTION], prefix=prefix_q), dtype=float))
        print(f"== {label} ==")
        _stats(d, q, "self-search")
        print(f"проектный вопрос, темы: {_theme_blob(t, d, pool)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

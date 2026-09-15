# -*- coding: utf-8 -*-
"""Bake-off эмбеддеров: e5-small (текущий) vs nomic-embed-text-v2-moe (Ollama).

Метрики на её архиве (102 авторских поста):
- самопоиск@1/@3 по запросу = первые 140 симв. поста (те же сид и крой, что
  в scripts/verify_retrieval_scoring.py);
- отдельно длинные посты (>1500 симв.) — там e5 размывается;
- проектный вопрос: темы гардероб/рецепт/доч в top-3.
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

import random

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
    with urllib.request.urlopen(req, timeout=300) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["embeddings"]


def _norm(m: np.ndarray) -> np.ndarray:
    return m / np.clip(np.linalg.norm(m, axis=1, keepdims=True), 1e-9, None)


def rates(docs: np.ndarray, queries: np.ndarray, k: int) -> tuple[float, float]:
    sims = queries @ docs.T
    top1 = (sims.argmax(axis=1) == np.arange(len(queries))).mean()
    topk = (np.argsort(-sims, axis=1)[:, :k] == np.arange(len(queries))[:, None]).any(axis=1).mean()
    return float(top1), float(topk)


async def main() -> int:
    async with SessionLocal() as session:
        rows = (
            (await session.execute(select(Post).order_by(desc(Post.id)))).scalars().all()
        )
        pool = [p for p in rows if _is_author_text(p) and (p.text or "").strip()]
    rng = random.Random(31)
    sample = rng.sample(pool, min(15, len(pool)))
    queries = [" ".join((p.text or "").split())[:140] for p in sample]
    long_idx = [i for i, p in enumerate(sample) if len(p.text or "") > 1500]
    docs_texts = [(p.text or "").strip()[:8000] for p in pool]

    emb = get_embedder()
    print("== e5-small (текущий, in-process onnx) ==")
    d_e5 = _norm(np.asarray(emb.embed(docs_texts, query=False), dtype=float))
    q_e5 = _norm(np.asarray(emb.embed(queries, query=True), dtype=float))
    q_e5_theme = _norm(np.asarray(emb.embed([QUESTION], query=True), dtype=float))
    sd1, sd3 = rates(d_e5[[pool.index(p) for p in sample]], q_e5, 3)
    ld1, ld3 = (
        rates(d_e5[[pool.index(sample[i]) for i in long_idx]], q_e5[long_idx], 3)
        if long_idx
        else (0.0, 0.0)
    )
    themes = [t for t in THEMES if t in _blob(q_e5_theme, d_e5, pool)]
    print(
        f"выборка(15): self@1={sd1:.0%} self@3={sd3:.0%}; "
        f"длинные({len(long_idx)}): self@1={ld1:.0%} self@3={ld3:.0%}; темы: {themes}"
    )

    for prefix_q, prefix_d, label in (
        (None, None, "nomic (без префиксов)"),
        ("search_query: ", "search_document: ", "nomic (search_ префиксы)"),
    ):
        print(f"== {label} ==")
        d = _norm(np.asarray(ollama_embed(docs_texts, prefix=prefix_d), dtype=float))
        q = _norm(np.asarray(ollama_embed(queries, prefix=prefix_q), dtype=float))
        qt = _norm(np.asarray(ollama_embed([QUESTION], prefix=prefix_q), dtype=float))
        idx = [pool.index(p) for p in sample]
        sd1, sd3 = rates(d[idx], q, 3)
        lidx = [idx[i] for i in long_idx]
        ld1, ld3 = rates(d[lidx], q[long_idx], 3) if long_idx else (0.0, 0.0)
        sims_q = (qt @ d.T)[0]
        top3 = [pool[i] for i in np.argsort(-sims_q)[:3]]
        blob = " ".join((p.text or "") for p in top3).lower()
        themes = [t for t in THEMES if t in blob]
        print(
            f"выборка(15): self@1={sd1:.0%} self@3={sd3:.0%}; "
            f"длинные({len(long_idx)}): self@1={ld1:.0%} self@3={ld3:.0%}; темы: {themes}"
        )
    return 0


def _blob(qvec: np.ndarray, docs: np.ndarray, pool) -> str:
    sims = (qvec @ docs.T)[0]
    top3 = [pool[i] for i in np.argsort(-sims)[:3]]
    return " ".join((p.text or "") for p in top3).lower()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

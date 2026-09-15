# -*- coding: utf-8 -*-
"""Совпадает ли сохранённый вектор #26 со свежим e5 его текста."""
import asyncio
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chromadb

from app.config import get_settings
from app.db.models import Post
from app.db.session import SessionLocal
from app.memory.embedder import get_embedder


async def main() -> int:
    async with SessionLocal() as session:
        p = await session.get(Post, 26)
        text = (p.text or "").strip()

    settings = get_settings()
    client = chromadb.PersistentClient(
        path=str(settings.resolve_path(settings.chroma_path))
    )
    col = client.get_or_create_collection("author_posts_e5")
    got = col.get(ids=["26"], include=["embeddings", "documents"])
    stored = np.asarray(got["embeddings"][0], dtype=float)
    stored = stored / np.linalg.norm(stored)
    emb = get_embedder()
    q_vec = np.asarray(emb.embed([text[:140]], query=True)[0], dtype=float)
    q_vec /= np.linalg.norm(q_vec)
    d_vec = np.asarray(emb.embed([text[:8000]], query=False)[0], dtype=float)
    d_vec /= np.linalg.norm(d_vec)
    print(f"cos(stored, fresh query-prefix) = {float(stored @ q_vec):.4f}")
    print(f"cos(stored, fresh full doc)     = {float(stored @ d_vec):.4f}")
    print(f"cos(fresh query, fresh doc)     = {float(q_vec @ d_vec):.4f}")
    print(f"doc хранит тот же текст: {got['documents'][0][:60] == text[:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

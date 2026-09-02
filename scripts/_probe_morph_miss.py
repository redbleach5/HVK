# -*- coding: utf-8 -*-
"""Разбор промахов verify_keyword_morphology: что за слова и куда делся пост."""
from __future__ import annotations

import asyncio
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import desc, select  # noqa: E402

import app.memory.retrieve as retrieve  # noqa: E402
from app.db.models import Post  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.memory.retrieve import (  # noqa: E402
    _STOP_KEYS,
    _key,
    _keyword_posts,
    _keys,
    posts_for_query,
)
from app.memory.store import _is_author_text  # noqa: E402

_WORD = re.compile(r"[а-яё]{5,}")
TARGETS = {44, 51, 83, 55}


async def main() -> int:
    retrieve.search_posts = lambda *args, **kwargs: []  # type: ignore[assignment]
    async with SessionLocal() as session:
        result = await session.execute(
            select(Post).order_by(desc(Post.engagement), desc(Post.id)).limit(120)
        )
        pool = [p for p in result.scalars() if _is_author_text(p)]
        rng = random.Random(11)
        sample = rng.sample(pool, 15)
        for post in sample:
            words = list(dict.fromkeys(_WORD.findall((post.text or "").lower())))
            if not words:
                continue
            word = rng.choice(words)
            if post.id not in TARGETS:
                continue
            inflected = word + ("м" if word[-1] in "аяоёеуюыи" else "а")
            keys_q = _keys(inflected)
            keys_t = _keys(post.text or "")
            raw = await _keyword_posts(session, inflected, limit=40)
            found = await posts_for_query(session, inflected, limit=10)
            print(
                f"#{post.id} word={word!r} inflected={inflected!r} "
                f"key={_key(inflected)!r} stop={_key(inflected) in _STOP_KEYS} "
                f"keys_q={sorted(keys_q)} hit_in_target={bool(keys_q & keys_t)} "
                f"keyword_hits={[p.id for p in raw[:6]]} "
                f"final={[p.id for p in found[:6]]}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

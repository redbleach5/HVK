# -*- coding: utf-8 -*-
"""Archive library: hits / similar / citeable desk. No LLM."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.context.engine import ContextEngine  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.memory.archive import Archive  # noqa: E402
from app.memory.retrieve import posts_for_query  # noqa: E402
from app.memory.store import MemoryStore  # noqa: E402
from app.memory.themes import is_promotional  # noqa: E402
from app.memory.working import clear_working  # noqa: E402

QUESTION = (
    "Кажется, я уже писала про осенний гардероб и мамин рецепт. "
    "Что лучше выложить в сообщество сейчас, чтобы не повторяться?"
)
TIRED = (
    "я уже ничего не соображаю. ребёнок весь день на мне. "
    "сил нет писать длинное. что лучше из того что у меня уже было?"
)


async def main() -> None:
    retrieve_src = (ROOT / "app" / "memory" / "retrieve.py").read_text(encoding="utf-8")
    if "query_wants_hits" in retrieve_src or "_HIT_HINTS" in retrieve_src:
        raise SystemExit("retrieve still has mood-hint branch")

    clear_working()
    async with SessionLocal() as session:
        memory = MemoryStore(session)
        raw = await memory.count_posts()
        author = await memory.count_author_posts()
        if author == 0:
            raise SystemExit("count_author_posts is 0")
        if author > raw:
            raise SystemExit("count_author_posts exceeded count_posts")

        archive = Archive(session)
        similar = await archive.similar(QUESTION, limit=6)
        via_retrieve = await posts_for_query(session, QUESTION, limit=6)
        if [p.id for p in similar] != [p.id for p in via_retrieve]:
            raise SystemExit("similar diverged from posts_for_query")
        if len(similar) < 2:
            raise SystemExit("similar returned too few posts")
        blob = " ".join((p.text or "") for p in similar).lower()
        if "гардероб" not in blob and "рецепт" not in blob and "доч" not in blob:
            raise SystemExit("similar missed author themes")
        if any(is_promotional(p.text or "") for p in similar):
            raise SystemExit("similar returned promo")

        hits = await archive.hits(90, 5)
        if not hits:
            raise SystemExit("hits empty")
        for post in hits:
            text = (post.text or "").lower()
            if "розыгрыш" in text or "сертификат на" in text:
                raise SystemExit(f"hits still has giveaway post #{post.id}")
            if is_promotional(post.text or ""):
                raise SystemExit(f"hits still has promo post #{post.id}")

        tired_similar = await archive.similar(TIRED, limit=6)
        if any(is_promotional(p.text or "") for p in tired_similar):
            raise SystemExit("tired similar returned promo")

        engine = ContextEngine(session)
        pack = await engine.pack(query=QUESTION)
        desk = pack.text.split("ПО ЭТОМУ ВОПРОСУ", 1)[0]
        if "Что лучше всего заходило" not in desk:
            raise SystemExit("desk missing hits section")
        hits_block = desk.split("Что лучше всего заходило", 1)[1]
        hits_block = hits_block.split("Незакрытые идеи", 1)[0]
        if "пост #" not in hits_block:
            raise SystemExit("hits in context missing post #")
        pack_ids = {p.id for p in pack.posts if p.id}
        if not pack_ids:
            raise SystemExit("pack has no posts")
        hit_in_pack = {p.id for p in hits if p.id} & pack_ids
        if not hit_in_pack:
            raise SystemExit("pack dropped desk hits")

        one = await archive.get(hits[0].id)
        if one is None or one.id != hits[0].id:
            raise SystemExit("get missed a live hit")

    clear_working()
    print("ok")


if __name__ == "__main__":
    asyncio.run(main())

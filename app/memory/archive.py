"""Архив как библиотека: хиты, похожие, недавние, один пост. Без LLM."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Post
from app.memory.retrieve import posts_for_query
from app.memory.store import MemoryStore, _is_author_text


class Archive:
    """Четыре операции над её текстами. Настроение не угадывает."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.memory = MemoryStore(session)

    async def hits(self, days: int = 90, limit: int = 3) -> list[Post]:
        """Живые тексты по вовлечённости, без розыгрышей и рекламы."""
        return await self.memory.top_posts(days, limit)

    async def similar(self, query: str, limit: int = 6) -> list[Post]:
        """Похожие по смыслу и словам. Хиты сюда не подмешиваются."""
        return await posts_for_query(self.session, query, limit=limit)

    async def recent(self, limit: int = 4) -> list[Post]:
        """Последние авторские посты."""
        return await self.memory.recent_posts(limit)

    async def get(self, post_id: int) -> Post | None:
        """Один живой пост или ничего."""
        post = await self.session.get(Post, int(post_id or 0))
        if post is None or not _is_author_text(post):
            return None
        return post

"""Контекстный движок: сезон, недавние посты, хиты, открытый план, память."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Post
from app.memory.citations import reader_notes
from app.memory.retrieve import posts_for_query
from app.memory.store import MemoryStore
from app.memory.working import remember_posts, working_prompt

_MONTH_SEASON = {
    12: "зима",
    1: "зима",
    2: "зима",
    3: "весна",
    4: "весна",
    5: "весна",
    6: "лето",
    7: "лето",
    8: "лето",
    9: "осень",
    10: "осень",
    11: "осень",
}

_MONTH_RU = [
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]


def current_season(now: datetime | None = None) -> str:
    """Русское имя сезона по месяцу."""
    now = now or datetime.now()
    return _MONTH_SEASON[now.month]


def format_date_ru(now: datetime | None = None) -> str:
    """Человеческая дата: «21 августа 2026»."""
    now = now or datetime.now()
    return f"{now.day} {_MONTH_RU[now.month]} {now.year}"


class ContextEngine:
    """Собирает своевременный контекст перед любым предложением агента."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.memory = MemoryStore(session)

    async def build(
        self,
        *,
        extra: str = "",
        query: str = "",
        retrieved: list[Post] | None = None,
    ) -> str:
        """Компактный фон + нужные тексты целиком, если есть вопрос."""
        now = datetime.now()
        season = current_season(now)
        recent = await self.memory.recent_posts(4)
        top = await self.memory.top_posts(42, 3)
        plan = await self.memory.open_plan_items()
        anti = await self.memory.antipathy_topics()
        memory_block = await self.memory.prompt_block()

        def _preview(post) -> str:
            date = post.published_at.strftime("%d.%m") if post.published_at else "без даты"
            snippet = (post.text or "").replace("\n", " ")[:140]
            theme = post.theme or "без темы"
            line = (
                f"- {date}, тема «{theme}», "
                f"вовлечённость {post.engagement:.0f}: {snippet}"
            )
            notes = reader_notes(post)
            if notes:
                line += f" | {notes}"
            return line

        def _full(post) -> str:
            date = post.published_at.strftime("%d.%m") if post.published_at else "без даты"
            theme = post.theme or "жизнь"
            body = (post.text or "").strip()
            if len(body) > 1600:
                body = body[:1600].rstrip() + "…"
            line = (
                f"— {date}, «{theme}», пост #{post.id}, "
                f"вовлечённость {post.engagement:.0f}:\n{body}"
            )
            notes = reader_notes(post)
            if notes:
                line += f"\n{notes}"
            return line

        recent_text = "\n".join(_preview(p) for p in recent) or "- публикаций ещё нет"
        top_text = "\n".join(_preview(p) for p in top) or "- мало данных"
        plan_text = (
            "\n".join(f"- [{item.status}] {item.title}" for item in plan)
            or "- открытых идей в плане нет"
        )
        anti_text = ", ".join(anti) if anti else "нет"

        q = (query or "").strip()
        if retrieved is not None:
            posts = list(retrieved)
        elif q:
            posts = await posts_for_query(self.session, q, limit=6)
            remember_posts(posts, reason=q)
        else:
            posts = []
        if retrieved is not None and q:
            remember_posts(posts, reason=q)
        retrieved_text = "\n\n".join(_full(p) for p in posts)
        session_text = working_prompt(exclude={p.id for p in posts})

        block = f"""
КОНТЕКСТ СЕЙЧАС
Сегодня {format_date_ru(now)}, сезон — {season}.
Система — ассистент, не автор. Не выдумывай факты из жизни автора.
Не предлагай то, что в антипатиях или было недавно.
Опирайся на тексты «по этому вопросу» и «уже открыто в диалоге», если они есть.

Недавние посты (кратко):
{recent_text}

Что лучше всего заходило за последние недели:
{top_text}

Незакрытые идеи в плане:
{plan_text}

Не повторять темы: {anti_text}

{memory_block}
""".strip()
        if retrieved_text:
            block = (
                f"{block}\n\n"
                "ПО ЭТОМУ ВОПРОСУ — её тексты целиком. Имена и факты — только отсюда, не выдумывай:\n"
                f"{retrieved_text}"
            )
        if session_text:
            block = (
                f"{block}\n\n"
                "УЖЕ ОТКРЫТО В ЭТОМ ДИАЛОГЕ:\n"
                f"{session_text}"
            )
        if extra:
            block = f"{block}\n\nДОПОЛНИТЕЛЬНО:\n{extra}"
        return block

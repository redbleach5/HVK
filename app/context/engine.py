"""Контекстный движок: сезон, недавние посты, хиты, открытый план, память."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Post
from app.memory.archive import Archive
from app.memory.citations import reader_notes
from app.memory.store import MemoryStore
from app.memory.working import remember_posts, working_post_ids, working_prompt

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

_HIT_BODY = 400
_FULL_BODY = 1600


def current_season(now: datetime | None = None) -> str:
    """Русское имя сезона по месяцу."""
    now = now or datetime.now()
    return _MONTH_SEASON[now.month]


def format_date_ru(now: datetime | None = None) -> str:
    """Человеческая дата: «21 августа 2026»."""
    now = now or datetime.now()
    return f"{now.day} {_MONTH_RU[now.month]} {now.year}"


def _unique_posts(*groups: list[Post]) -> list[Post]:
    seen: set[int] = set()
    out: list[Post] = []
    for group in groups:
        for post in group:
            pid = getattr(post, "id", None)
            if pid is None or pid in seen:
                continue
            seen.add(pid)
            out.append(post)
    return out


@dataclass
class ContextPack:
    """Текст для модели и те же посты, что в нём — для карточки «почему»."""

    text: str
    posts: list[Post] = field(default_factory=list)


class ContextEngine:
    """Собирает своевременный контекст перед любым предложением агента."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.memory = MemoryStore(session)
        self.archive = Archive(session)

    async def build(
        self,
        *,
        extra: str = "",
        query: str = "",
        retrieved: list[Post] | None = None,
        with_session: bool = True,
        include_voice: bool = True,
    ) -> str:
        """Компактный фон + нужные тексты целиком, если есть вопрос."""
        pack = await self.pack(
            extra=extra,
            query=query,
            retrieved=retrieved,
            with_session=with_session,
            include_voice=include_voice,
        )
        return pack.text

    async def pack(
        self,
        *,
        extra: str = "",
        query: str = "",
        retrieved: list[Post] | None = None,
        with_session: bool = True,
        include_voice: bool = True,
    ) -> ContextPack:
        """Стол + вопрос: хиты с номерами, similar целиком, pack для grounding.

        with_session=False — агентам вне диалога (идеи, редактор, аудит):
        рабочий набор чата не должен утекать в их промпт.
        include_voice=False — когда полный профиль голоса показан отдельно.
        """
        now = datetime.now()
        season = current_season(now)
        recent = await self.archive.recent(4)
        hits = await self.archive.hits(42, 3)
        plan = await self.memory.open_plan_items()
        anti = await self.memory.antipathy_topics()

        q = (query or "").strip()
        if retrieved is not None:
            similar = list(retrieved)
        elif q:
            similar = await self.archive.similar(q, limit=6)
        else:
            similar = []
        if with_session and similar and q:
            remember_posts(similar, reason=q)

        similar_ids = {p.id for p in similar if p.id}
        hit_ids = {p.id for p in hits if p.id}
        recent_text = "\n".join(_preview(p) for p in recent) or "- публикаций ещё нет"
        # Хиты, уже показанные целиком в «ПО ЭТОМУ ВОПРОСУ», кратко не повторяем.
        hits_text = (
            "\n".join(_hit_cite(p) for p in hits if p.id not in similar_ids)
            or "- (лучшее уже показано целиком ниже)"
        )
        plan_text = (
            "\n".join(f"- [{item.status}] {item.title}" for item in plan)
            or "- открытых идей в плане нет"
        )
        anti_text = ", ".join(anti) if anti else "нет"
        memory_block = await self.memory.prompt_block(include_voice=include_voice)

        retrieved_text = "\n\n".join(_full(p) for p in similar)
        session_text = (
            working_prompt(exclude=similar_ids | hit_ids) if with_session else ""
        )

        working: list[Post] = []
        if with_session:
            for pid in working_post_ids():
                if pid in similar_ids or pid in hit_ids:
                    continue
                post = await self.archive.get(pid)
                if post is not None:
                    working.append(post)

        block = f"""
КОНТЕКСТ СЕЙЧАС
Сегодня {format_date_ru(now)}, сезон — {season}.
Система — ассистент, не автор. Не выдумывай факты из жизни автора.
Не предлагай то, что в антипатиях — даже другими словами. В реплике запреты не читай.
Опирайся на тексты «по этому вопросу» и «уже открыто в диалоге», если они есть.
В её цитатах ищи живой жест, не общее слово «уют». Если опираешься — номер поста.
Вещь в реплике — только из цитаты этого номера. Нет в тексте — не додумывай чайник, свитер, свет.

Недавние посты (кратко):
{recent_text}

Что лучше всего заходило за последние недели:
{hits_text}

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
        return ContextPack(text=block, posts=_unique_posts(hits, similar, working))


def _preview(post: Post) -> str:
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


def _hit_cite(post: Post) -> str:
    date = post.published_at.strftime("%d.%m") if post.published_at else "без даты"
    snippet = (post.text or "").replace("\n", " ").strip()
    if len(snippet) > _HIT_BODY:
        snippet = snippet[:_HIT_BODY].rstrip() + "…"
    theme = post.theme or "жизнь"
    pid = getattr(post, "id", None) or "?"
    line = (
        f"- {date}, «{theme}», пост #{pid}, "
        f"вовлечённость {post.engagement:.0f}: {snippet}"
    )
    notes = reader_notes(post)
    if notes:
        line += f" | {notes}"
    return line


def _full(post: Post) -> str:
    date = post.published_at.strftime("%d.%m") if post.published_at else "без даты"
    theme = post.theme or "жизнь"
    body = (post.text or "").strip()
    if len(body) > _FULL_BODY:
        body = body[:_FULL_BODY].rstrip() + "…"
    line = (
        f"— {date}, «{theme}», пост #{post.id}, "
        f"вовлечённость {post.engagement:.0f}:\n{body}"
    )
    notes = reader_notes(post)
    if notes:
        line += f"\n{notes}"
    return line

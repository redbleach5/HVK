"""Контекстный движок: сезон, недавние посты, хиты, открытый план, память."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.store import MemoryStore

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

    async def build(self, *, extra: str = "") -> str:
        """Возвращает текст, который нужно подставить в каждый промпт."""
        now = datetime.now()
        season = current_season(now)
        recent = await self.memory.recent_posts(8)
        top = await self.memory.top_posts(42, 5)
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
            comments = post.comments or []
            if comments:
                bits: list[str] = []
                for raw in comments[:3]:
                    if isinstance(raw, dict):
                        t = str(raw.get("text") or raw.get("message") or "").strip()
                    else:
                        t = str(raw).strip()
                    if t:
                        bits.append(t[:90])
                if bits:
                    line += " | читатели: " + "; ".join(bits)
            return line

        recent_text = "\n".join(_preview(p) for p in recent) or "- публикаций ещё нет"
        top_text = "\n".join(_preview(p) for p in top) or "- мало данных"
        plan_text = (
            "\n".join(f"- [{item.status}] {item.title}" for item in plan)
            or "- открытых идей в плане нет"
        )
        anti_text = ", ".join(anti) if anti else "нет"

        block = f"""
КОНТЕКСТ СЕЙЧАС
Сегодня {format_date_ru(now)}, сезон — {season}.
Система — ассистент, не автор. Не выдумывай факты из жизни автора.
Не предлагай то, что в антипатиях или было недавно.

Недавние посты:
{recent_text}

Что лучше всего заходило за последние недели:
{top_text}

Незакрытые идеи в плане:
{plan_text}

Не повторять темы: {anti_text}

{memory_block}
""".strip()
        if extra:
            block = f"{block}\n\nДОПОЛНИТЕЛЬНО:\n{extra}"
        return block

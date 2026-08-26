"""Структурированная память автора: не лог, а знания для промпта."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.themes import is_promotional
from app.db.models import (
    ActivityLog,
    Antipathy,
    AuthorProfile,
    Digest,
    Idea,
    Lesson,
    PlanItem,
    Post,
    Preference,
    Rhythm,
    Suggestion,
    VoiceProfile,
)

logger = logging.getLogger(__name__)


def _is_author_text(post: Post) -> bool:
    """Живой текст автора, не пустая подпись и не реклама со стены."""
    text = (post.text or "").strip()
    return bool(text) and not is_promotional(text)


class MemoryStore:
    """Читает и обновляет память. Отдаёт компактный блок для LLM."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_profile(self) -> AuthorProfile:
        """Возвращает единственный профиль автора."""
        profile = await self.session.get(AuthorProfile, 1)
        if profile is None:
            profile = AuthorProfile(id=1, blog_name="Красивое в обычном")
            self.session.add(profile)
            await self.session.flush()
        return profile

    async def prompt_block(self, *, extra: str = "") -> str:
        """Собирает знания, которые модель может прочитать целиком."""
        profile = await self.get_profile()
        prefs = await self.session.execute(select(Preference).order_by(Preference.kind, Preference.key))
        lessons = await self.session.execute(
            select(Lesson).order_by(desc(Lesson.created_at)).limit(12)
        )
        antipathies = await self._active_antipathies()
        rhythm_rows = await self.session.execute(
            select(Rhythm).order_by(desc(Rhythm.posts_count)).limit(5)
        )
        voice = await self.latest_voice()

        pref_lines = [
            f"- [{p.kind}] {p.key}: {p.value} (вес {p.weight:.1f})"
            for p in prefs.scalars()
        ] or ["- пока пусто — узнаём автора по ходу"]
        lesson_lines = [
            f"- ({row.outcome}) {row.title}: {row.why}"
            for row in lessons.scalars()
        ] or ["- уроков ещё нет"]
        anti_lines = [
            f"- не предлагать «{a.topic}»: {a.reason}"
            for a in antipathies
        ] or ["- явных запретов нет"]
        weekday_names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
        rhythm_lines = [
            f"- {weekday_names[r.weekday % 7]} около {r.hour:02d}:00 "
            f"({r.posts_count} постов, вовлечённость {r.avg_engagement:.1f})"
            for r in rhythm_rows.scalars()
        ] or ["- ритм ещё не ясен"]
        voice_text = "ещё не собран"
        if voice:
            p = voice.profile
            voice_text = (
                f"тон: {p.get('tone', '—')}; обращение: {p.get('address', '—')}; "
                f"средняя длина: {p.get('avg_length_chars', '—')}; "
                f"эмодзи: {p.get('emoji_habits', '—')}"
            )

        block = f"""
ПАМЯТЬ АВТОРА
Блог: {profile.blog_name}
О себе: {profile.about or "ещё не рассказала"}

Предпочтения:
{chr(10).join(pref_lines)}

Уроки (что заходило и почему):
{chr(10).join(lesson_lines)}

Антипатии и недавние повторы:
{chr(10).join(anti_lines)}

Ритм публикаций:
{chr(10).join(rhythm_lines)}

Голос: {voice_text}
""".strip()
        if extra:
            block = f"{block}\n\n{extra}"
        return block

    async def latest_voice(self) -> Optional[VoiceProfile]:
        """Последняя версия профиля голоса."""
        result = await self.session.execute(
            select(VoiceProfile).order_by(desc(VoiceProfile.version)).limit(1)
        )
        return result.scalar_one_or_none()

    async def _active_antipathies(self) -> list[Antipathy]:
        now = datetime.utcnow()
        result = await self.session.execute(select(Antipathy))
        items = []
        for item in result.scalars():
            if item.expires_at is None or item.expires_at > now:
                items.append(item)
        return items

    async def antipathy_topics(self) -> list[str]:
        """Темы, которые нельзя предлагать повторно."""
        return [a.topic.lower() for a in await self._active_antipathies()]

    async def add_preference(self, kind: str, key: str, value: str, weight: float = 1.0) -> Preference:
        """Добавляет или усиливает предпочтение."""
        result = await self.session.execute(
            select(Preference).where(Preference.kind == kind, Preference.key == key)
        )
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = value
            existing.weight = min(existing.weight + 0.3, 5.0)
            return existing
        pref = Preference(kind=kind, key=key, value=value, weight=weight)
        self.session.add(pref)
        await self.session.flush()
        return pref

    async def add_lesson(
        self,
        title: str,
        outcome: str,
        why: str,
        *,
        source: str = "feedback",
        related_post_id: int | None = None,
        suggestion_id: int | None = None,
    ) -> Lesson:
        """Записывает урок с обоснованием."""
        lesson = Lesson(
            title=title,
            outcome=outcome,
            why=why,
            source=source,
            related_post_id=related_post_id,
            suggestion_id=suggestion_id,
        )
        self.session.add(lesson)
        await self.session.flush()
        return lesson

    async def add_antipathy(self, topic: str, reason: str, days: int | None = 45) -> Antipathy:
        """Помечает тему как нежелательную на ближайшее время."""
        expires = datetime.utcnow() + timedelta(days=days) if days else None
        item = Antipathy(topic=topic, reason=reason, expires_at=expires)
        self.session.add(item)
        await self.session.flush()
        return item

    async def refresh_rhythm(self) -> None:
        """Пересчитывает ритм по датам публикаций."""
        result = await self.session.execute(
            select(Post).where(Post.published_at.is_not(None))
        )
        buckets: dict[tuple[int, int], list[float]] = {}
        for post in result.scalars():
            if post.published_at is None:
                continue
            key = (post.published_at.weekday(), post.published_at.hour)
            buckets.setdefault(key, []).append(post.engagement)
        await self.session.execute(delete(Rhythm))
        for (weekday, hour), values in buckets.items():
            self.session.add(
                Rhythm(
                    weekday=weekday,
                    hour=hour,
                    posts_count=len(values),
                    avg_engagement=sum(values) / len(values),
                )
            )
        await self.session.flush()

    async def rhythm_hint(self) -> str:
        """Одна тёплая строка: когда обычно лучше заходит."""
        weekday_names = ["понедельник", "вторник", "среду", "четверг", "пятницу", "субботу", "воскресенье"]
        result = await self.session.execute(
            select(Rhythm).order_by(desc(Rhythm.avg_engagement), desc(Rhythm.posts_count)).limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return "Ритм ещё не ясен — после нескольких постов подскажу, когда обычно теплее."
        day = weekday_names[row.weekday % 7]
        return f"Обычно лучше заходит в {day} около {row.hour:02d}:00"

    async def save_suggestion(
        self,
        kind: str,
        title: str,
        payload: dict[str, Any],
        why: dict[str, Any],
        *,
        parent_id: int | None = None,
    ) -> Suggestion:
        """Фиксирует предложение агента до реакции автора."""
        item = Suggestion(
            kind=kind,
            title=title[:240],
            payload=payload,
            why=why,
            status="pending",
            parent_id=parent_id,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def log(self, action: str, summary: str, extra: dict[str, Any] | None = None) -> None:
        """Пишет человеческую запись в историю действий."""
        self.session.add(
            ActivityLog(action=action, summary=summary, extra=extra or {})
        )
        await self.session.flush()

    async def recent_activity(self, limit: int = 8) -> list[ActivityLog]:
        """Последние действия для дашборда."""
        result = await self.session.execute(
            select(ActivityLog).order_by(desc(ActivityLog.created_at)).limit(limit)
        )
        return list(result.scalars())

    async def recent_posts(self, limit: int = 8) -> list[Post]:
        """Недавние посты автора. Вставленные без даты не тонут в конце."""
        result = await self.session.execute(
            select(Post)
            .order_by(
                desc(func.coalesce(Post.published_at, Post.created_at)),
                desc(Post.id),
            )
            .limit(max(limit * 5, 30))
        )
        out: list[Post] = []
        for post in result.scalars():
            if not _is_author_text(post):
                continue
            out.append(post)
            if len(out) >= limit:
                break
        return out

    async def top_posts(self, days: int = 45, limit: int = 5) -> list[Post]:
        """Лучшие посты за окно времени."""
        since = datetime.utcnow() - timedelta(days=days)
        result = await self.session.execute(
            select(Post)
            .where(Post.published_at.is_not(None), Post.published_at >= since)
            .order_by(desc(Post.engagement))
            .limit(max(limit * 4, 20))
        )
        rows = [p for p in result.scalars() if _is_author_text(p)][:limit]
        if rows:
            return rows
        fallback = await self.session.execute(
            select(Post).order_by(desc(Post.engagement)).limit(max(limit * 4, 20))
        )
        return [p for p in fallback.scalars() if _is_author_text(p)][:limit]

    async def open_plan_items(self) -> list[PlanItem]:
        """Незакрытые пункты плана."""
        result = await self.session.execute(
            select(PlanItem)
            .where(PlanItem.status != "published")
            .order_by(PlanItem.scheduled_date.is_(None), PlanItem.scheduled_date.asc(), PlanItem.id)
        )
        return list(result.scalars())

    async def latest_digest(self) -> Optional[Digest]:
        """Последний утренний дайджест."""
        result = await self.session.execute(
            select(Digest).order_by(desc(Digest.created_at)).limit(1)
        )
        return result.scalar_one_or_none()

    async def count_posts(self) -> int:
        """Число постов в архиве."""
        result = await self.session.execute(select(func.count(Post.id)))
        return int(result.scalar_one())

    async def recent_idea_themes(self, limit: int = 20) -> list[str]:
        """Темы недавних идей — чтобы не повторяться."""
        result = await self.session.execute(
            select(Idea.theme).order_by(desc(Idea.created_at)).limit(limit)
        )
        return [row[0] for row in result.all()]

    async def recent_ideas(
        self,
        limit: int = 6,
        *,
        statuses: tuple[str, ...] | None = None,
    ) -> list[Idea]:
        """Последние идеи из памяти, без генерации."""
        stmt = select(Idea).order_by(desc(Idea.created_at)).limit(limit)
        if statuses:
            stmt = (
                select(Idea)
                .where(Idea.status.in_(statuses))
                .order_by(desc(Idea.created_at))
                .limit(limit)
            )
        result = await self.session.execute(stmt)
        return list(result.scalars())

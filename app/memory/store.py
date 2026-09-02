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
    AudienceCache,
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

    async def prompt_block(
        self, *, extra: str = "", include_voice: bool = True
    ) -> str:
        """Собирает знания, которые модель может прочитать целиком.

        include_voice=False — когда агент (например, редактор) показывает
        полный профиль голоса отдельно: дублировать сводку не нужно.
        """
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
        voice_text = "ещё не собран" if include_voice else ""
        if voice and include_voice:
            p = voice.profile or {}
            voice_text = (
                f"тон: {p.get('tone', '—')}; обращение: {p.get('address', '—')}; "
                f"средняя длина: {p.get('avg_length_chars', '—')}; "
                f"эмодзи: {p.get('emoji_habits', '—')}"
            )
            lex = p.get("lexicon") or p.get("frequent_words") or []
            if lex:
                voice_text += "; слова: " + ", ".join(str(w) for w in lex[:8])
            fresh_n = p.get("fresh_posts_used")
            if fresh_n:
                voice_text += (
                    f". Сегодняшний голос — по {fresh_n} свежим постам"
                )
                older_n = p.get("older_posts_used") or 0
                if older_n:
                    voice_text += "; старые только нить, не тон"
                voice_text += "."
            else:
                voice_text += ". Недавние посты важнее старого архива."
            # Интонации и запреты — для всех агентов, не только для редактора:
            # чат и идеи должны слышать голос, а не только знать длину поста.
            phrases = [
                str(s).strip()
                for s in (p.get("sample_phrases") or [])
                if str(s).strip()
            ][:3]
            if phrases:
                voice_text += (
                    "\nКак звучит её интонация (живой жест, не цитаты для копирования): "
                    + " | ".join(f"«{s}»" for s in phrases)
                )
            forbidden = [
                str(s).strip()
                for s in (p.get("forbidden_vibes") or [])
                if str(s).strip()
            ][:4]
            if forbidden:
                voice_text += (
                    "\nЧего в её голосе нет: " + ", ".join(forbidden) + "."
                )

        style_lines = await self._style_lesson_lines(limit=6)

        voice_line = f"Голос: {voice_text}" if include_voice else ""

        block = f"""
ПАМЯТЬ АВТОРА
Блог: {profile.blog_name}
О себе: {profile.about or "ещё не рассказала"}

Предпочтения:
{chr(10).join(pref_lines)}

Уроки (что заходило и почему):
{chr(10).join(lesson_lines)}

Антипатии (не предлагать даже близкое по смыслу):
{chr(10).join(anti_lines)}

Ритм публикаций:
{chr(10).join(rhythm_lines)}

{voice_line}
""".strip()
        if style_lines:
            block = (
                f"{block}\n\nЧего не подходит в правках (не повторять):\n"
                + "\n".join(style_lines)
            )
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

    async def is_semantically_blocked(self, topic: str, *, threshold: float = 0.78) -> tuple[bool, str | None]:
        """Проверяет, не является ли тема семантически близкой к отвергнутой.

        Возвращает (blocked, matched_antipathy_topic). Ловит «Утренний чай»
        когда отвергнута «Завтрак с чаем» — точное совпадение по строке этого не видит.

        Порог 0.78 = косинусное сходство ≥ 0.78 (empirically «тот же смысл»).
        Если ChromaDB недоступен — fallback на точное совпадение.
        """
        topic = (topic or "").strip()
        if not topic:
            return False, None
        active = await self._active_antipathies()
        if not active:
            return False, None

        # 1. Точное совпадение — быстро, без сети
        topic_low = topic.lower()
        for a in active:
            if a.topic.lower() == topic_low:
                return True, a.topic

        # 2. Семантическое сравнение через эмбеддинги ChromaDB
        try:
            from app.memory.chroma import _get_embedder

            embedder = _get_embedder()
            antipathy_docs = [a.topic for a in active if a.topic.strip()]
            if not antipathy_docs:
                return False, None

            # Эмбеддинги: target и все antipathy-темы одним батчем
            target_emb = embedder([topic])
            anti_embs = embedder(antipathy_docs)

            # ChromaDB embedder может возвращать list[list[float]] или numpy
            import numpy as np

            target_vec = np.asarray(target_emb[0] if isinstance(target_emb, list) else target_emb)
            # anti_embs может быть [vec1, vec2, ...] или 2D-массив
            if isinstance(anti_embs, list):
                anti_matrix = np.asarray(anti_embs)
            else:
                anti_matrix = np.asarray(anti_embs)
            if anti_matrix.ndim == 1:
                anti_matrix = anti_matrix.reshape(1, -1)

            # Косинусное сходство через матричное умножение
            target_norm = np.linalg.norm(target_vec)
            if target_norm == 0:
                return False, None
            anti_norms = np.linalg.norm(anti_matrix, axis=1)
            denom = anti_norms * target_norm
            # Защита от деления на 0
            denom = np.where(denom == 0, 1.0, denom)
            sims = (anti_matrix @ target_vec) / denom

            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])
            if best_sim >= threshold:
                return True, antipathy_docs[best_idx]
        except Exception:
            logger.debug("Semantic antipathy check failed", exc_info=True)
            return False, None

        return False, None

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

    async def prune_old_lessons(self, *, days: int = 730) -> int:
        """Удаляет уроки старше N дней. По умолчанию TTL = 2 года.

        Старые уроки размывают сигнал — автор меняется со временем, и урок 2-летней
        давности про «не зашёл тёплый свитер» больше не релевантен. Preference
        тоже накапливаются, но у них нет TTL по дизайну (предпочтения стабильнее).
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = await self.session.execute(
            delete(Lesson).where(Lesson.created_at < cutoff)
        )
        deleted = int(result.rowcount or 0)
        if deleted:
            logger.info("Удалено %s устаревших уроков (старше %s дней)", deleted, days)
        return deleted

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
            if post.published_at is None or not _is_author_text(post):
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
        """Все строки в таблице постов, включая рекламу со стены."""
        result = await self.session.execute(select(func.count(Post.id)))
        return int(result.scalar_one())

    async def count_author_posts(self) -> int:
        """Живые тексты автора — гейт агентов и онбординга."""
        result = await self.session.execute(select(Post))
        return sum(1 for post in result.scalars() if _is_author_text(post))

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

    async def recent_style_lessons(self, *, limit: int = 8) -> list[Lesson]:
        """Отвергнутые правки редактора — только kind=edit."""
        result = await self.session.execute(
            select(Lesson)
            .join(Suggestion, Lesson.suggestion_id == Suggestion.id)
            .where(
                Lesson.source == "feedback",
                Lesson.outcome.in_(["fail", "mixed"]),
                Suggestion.kind == "edit",
            )
            .order_by(desc(Lesson.created_at))
            .limit(limit)
        )
        return list(result.scalars())

    async def _style_lesson_lines(self, *, limit: int = 6) -> list[str]:
        """Короткие строки для промпта: чего в правках не повторять."""
        lines: list[str] = []
        for lesson in await self.recent_style_lessons(limit=limit):
            title = (lesson.title or "").replace("Не зашло:", "").strip()
            why_text = (lesson.why or "").strip()
            if not title:
                continue
            line = f"- {title}"
            if why_text and why_text != title:
                line += f" ({why_text[:120]})"
            lines.append(line)
        return lines

    async def posts_signature(self) -> str:
        """Стабильная подпись архива: count + max(updated_at|id)."""
        result = await self.session.execute(
            select(
                func.count(Post.id),
                func.max(Post.id),
                func.max(func.coalesce(Post.published_at, Post.created_at)),
            )
        )
        n, max_id, max_date = result.one()
        if not n:
            return "empty"
        date_str = max_date.isoformat() if max_date else "no-date"
        return f"n{n}-i{max_id or 0}-d{date_str[:19]}"

    async def get_audience_cache(self, signature: str) -> Optional[AudienceCache]:
        """Возвращает кэшированный отчёт, если подпись совпадает."""
        result = await self.session.execute(
            select(AudienceCache).where(AudienceCache.posts_signature == signature).limit(1)
        )
        return result.scalar_one_or_none()

    async def save_audience_cache(
        self,
        signature: str,
        report: dict[str, Any],
        *,
        suggestion_id: int | None = None,
        posts_count: int = 0,
    ) -> AudienceCache:
        """Стирает старый кэш и кладёт новый. Старые suggestion_id остаются."""
        await self.session.execute(
            delete(AudienceCache).where(AudienceCache.posts_signature != signature)
        )
        cached = AudienceCache(
            posts_signature=signature,
            posts_count=posts_count,
            report=report,
            suggestion_id=suggestion_id,
        )
        self.session.add(cached)
        await self.session.flush()
        return cached

    async def invalidate_audience_cache(self) -> None:
        """Полный сброс кэша — когда архив изменился до неузнаваемости."""
        await self.session.execute(delete(AudienceCache))
        await self.session.flush()

    async def posts_in_range(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[Post]:
        """Посты в окне времени — для аналитики с фильтром."""
        stmt = select(Post).where(Post.published_at.is_not(None))
        if since:
            stmt = stmt.where(Post.published_at >= since)
        if until:
            stmt = stmt.where(Post.published_at <= until)
        stmt = stmt.order_by(Post.published_at.asc())
        result = await self.session.execute(stmt)
        return [p for p in result.scalars() if _is_author_text(p)]

    async def engagement_by_theme(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """Средняя вовлечённость и постов по темам — для разбивки."""
        posts = await self.posts_in_range(since=since, until=until)
        buckets: dict[str, list[Post]] = {}
        for p in posts:
            theme = (p.theme or "без темы").strip() or "без темы"
            buckets.setdefault(theme, []).append(p)
        rows = []
        for theme, items in buckets.items():
            eng = sum(p.engagement for p in items) / len(items) if items else 0
            rows.append({
                "theme": theme,
                "posts_count": len(items),
                "avg_engagement": eng,
                "total_engagement": sum(p.engagement for p in items),
                "total_likes": sum(p.likes for p in items),
                "total_comments": sum(p.comments_count for p in items),
                "total_views": sum(p.views for p in items),
            })
        rows.sort(key=lambda r: r["avg_engagement"], reverse=True)
        return rows[:limit]

    async def engagement_heatmap(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Тепловая карта по дням недели × часам — когда лучше постить."""
        posts = await self.posts_in_range(since=since, until=until)
        buckets: dict[tuple[int, int], list[float]] = {}
        for p in posts:
            if p.published_at is None:
                continue
            key = (p.published_at.weekday(), p.published_at.hour)
            buckets.setdefault(key, []).append(p.engagement)
        return [
            {
                "weekday": wd,
                "hour": h,
                "posts_count": len(values),
                "avg_engagement": sum(values) / len(values) if values else 0,
            }
            for (wd, h), values in buckets.items()
        ]

    async def engagement_stats(
        self,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        """Сводка по окну: суммы и средние."""
        posts = await self.posts_in_range(since=since, until=until)
        if not posts:
            return {
                "posts_count": 0,
                "avg_engagement": 0,
                "total_likes": 0,
                "total_comments": 0,
                "total_views": 0,
            }
        return {
            "posts_count": len(posts),
            "avg_engagement": sum(p.engagement for p in posts) / len(posts),
            "total_likes": sum(p.likes for p in posts),
            "total_comments": sum(p.comments_count for p in posts),
            "total_views": sum(p.views for p in posts),
            "best_engagement": max(p.engagement for p in posts),
            "worst_engagement": min(p.engagement for p in posts),
        }

"""Модели SQLAlchemy: память, посты, идеи, план, предложения."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс моделей."""


class AuthorProfile(Base):
    """Профиль автора блога. Одна запись на установку."""

    __tablename__ = "author_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blog_name: Mapped[str] = mapped_column(String(200), default="Красивое в обычном")
    about: Mapped[str] = mapped_column(Text, default="")
    onboarding_step: Mapped[int] = mapped_column(Integer, default=0)
    onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Post(Base):
    """Пост из архива VK."""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vk_post_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    text: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments_count: Mapped[int] = mapped_column(Integer, default=0)
    reposts: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)
    engagement: Mapped[float] = mapped_column(Float, default=0.0)
    theme: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    photo_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    comments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    idea_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ideas.id"), nullable=True)
    plan_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("plan_items.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class VoiceProfile(Base):
    """Версии живого профиля голоса."""

    __tablename__ = "voice_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(40), default="import")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Preference(Base):
    """Предпочтения автора: темы, цвета, форматы, ритуалы."""

    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(Text, default="")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Lesson(Base):
    """Урок: что зашло или провалилось и почему."""

    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(240))
    outcome: Mapped[str] = mapped_column(String(20))  # success | fail | mixed
    why: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(40), default="feedback")
    related_post_id: Mapped[Optional[int]] = mapped_column(ForeignKey("posts.id"), nullable=True)
    suggestion_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suggestions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Antipathy(Base):
    """То, что автор отвергла или уже недавно делала."""

    __tablename__ = "antipathies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(String(240))
    reason: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Rhythm(Base):
    """Ритм публикаций: день недели и час."""

    __tablename__ = "rhythm"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    weekday: Mapped[int] = mapped_column(Integer)
    hour: Mapped[int] = mapped_column(Integer)
    posts_count: Mapped[int] = mapped_column(Integer, default=1)
    avg_engagement: Mapped[float] = mapped_column(Float, default=0.0)


class Suggestion(Base):
    """Любое предложение системы, по которому автор даёт обратную связь."""

    __tablename__ = "suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(240), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    why: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|accepted|rejected
    feedback_note: Mapped[str] = mapped_column(Text, default="")
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suggestions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    children: Mapped[list["Suggestion"]] = relationship("Suggestion", backref="parent", remote_side=[id])


class Idea(Base):
    """Идея контента."""

    __tablename__ = "ideas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    suggestion_id: Mapped[Optional[int]] = mapped_column(ForeignKey("suggestions.id"), nullable=True)
    theme: Mapped[str] = mapped_column(String(240))
    format: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    personal_angle: Mapped[str] = mapped_column(Text, default="")
    visual: Mapped[str] = mapped_column(Text, default="")
    effort: Mapped[str] = mapped_column(String(20), default="medium")
    why_now: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    plan_items: Mapped[list["PlanItem"]] = relationship("PlanItem", back_populates="idea")


class PlanItem(Base):
    """Пункт недельного плана: задумано → написано → опубликовано."""

    __tablename__ = "plan_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    idea_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ideas.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(240))
    draft_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="conceived")  # conceived|written|published
    scheduled_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    published_post_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    idea: Mapped[Optional[Idea]] = relationship("Idea", back_populates="plan_items")


class Digest(Base):
    """Утреннее контекстное резюме. Не пуш — ждёт, пока автор откроет дашборд."""

    __tablename__ = "digests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    body: Mapped[str] = mapped_column(Text)
    highlights: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    idea_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ActivityLog(Base):
    """Последние действия для истории в интерфейсе."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str] = mapped_column(Text)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ChatMessage(Base):
    """Сообщение чата с редакцией."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    cards: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    suggestion_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

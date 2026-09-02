"""Диалоги чата: несколько тем, удаление."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatMessage, ChatThread
from app.memory.store import MemoryStore
from app.memory.working import clear_working
from app.schemas.api import ChatThreadOut

logger = logging.getLogger(__name__)

_DEFAULT_TITLE = "Новый диалог"


def _out(row: ChatThread) -> ChatThreadOut:
    return ChatThreadOut(
        id=row.id,
        title=row.title or _DEFAULT_TITLE,
        created_at=row.created_at.isoformat() if row.created_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
        message_count=int(getattr(row, "_message_count", 0) or 0),
    )


async def list_threads(session: AsyncSession) -> list[ChatThreadOut]:
    """Все диалоги, свежие сверху."""
    count_sq = (
        select(ChatMessage.thread_id, func.count(ChatMessage.id).label("n"))
        .group_by(ChatMessage.thread_id)
        .subquery()
    )
    result = await session.execute(
        select(ChatThread, count_sq.c.n)
        .outerjoin(count_sq, ChatThread.id == count_sq.c.thread_id)
        .order_by(desc(ChatThread.updated_at), desc(ChatThread.id))
    )
    out: list[ChatThreadOut] = []
    for thread, n in result.all():
        thread._message_count = n or 0  # type: ignore[attr-defined]
        out.append(_out(thread))
    return out


async def create_thread(session: AsyncSession, *, title: str = _DEFAULT_TITLE) -> ChatThreadOut:
    row = ChatThread(title=title.strip()[:120] or _DEFAULT_TITLE)
    session.add(row)
    await session.flush()
    await MemoryStore(session).log("chat", f"Новый диалог: {row.title}")
    await session.commit()
    await session.refresh(row)
    row._message_count = 0  # type: ignore[attr-defined]
    return _out(row)


async def get_thread(session: AsyncSession, thread_id: int) -> ChatThread | None:
    return await session.get(ChatThread, thread_id)


async def ensure_thread(session: AsyncSession, thread_id: int | None) -> ChatThread:
    """Возвращает существующий диалог или создаёт первый."""
    if thread_id is not None:
        row = await get_thread(session, thread_id)
        if row is not None:
            return row
    result = await session.execute(
        select(ChatThread).order_by(desc(ChatThread.updated_at), desc(ChatThread.id)).limit(1)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row
    created = await create_thread(session)
    row = await get_thread(session, created.id)
    assert row is not None
    return row


async def delete_thread(session: AsyncSession, thread_id: int) -> bool:
    row = await get_thread(session, thread_id)
    if row is None:
        return False
    await session.execute(delete(ChatMessage).where(ChatMessage.thread_id == thread_id))
    await session.delete(row)
    await MemoryStore(session).log("chat", f"Удалён диалог: {row.title}")
    await session.commit()
    clear_working()
    return True


async def touch_thread(
    session: AsyncSession,
    thread_id: int,
    *,
    message: str = "",
) -> None:
    """Обновляет updated_at; первое сообщение — заголовок."""
    row = await get_thread(session, thread_id)
    if row is None:
        return
    row.updated_at = datetime.utcnow()
    text = (message or "").strip()
    if text and (row.title or _DEFAULT_TITLE) == _DEFAULT_TITLE:
        row.title = text.replace("\n", " ")[:48]
    await session.flush()


async def clear_thread_messages(session: AsyncSession, thread_id: int) -> bool:
    row = await get_thread(session, thread_id)
    if row is None:
        return False
    await session.execute(delete(ChatMessage).where(ChatMessage.thread_id == thread_id))
    await MemoryStore(session).log("chat", f"Очищен диалог: {row.title}")
    await session.commit()
    clear_working()
    return True


async def migrate_orphan_messages(session: AsyncSession) -> None:
    """Старые сообщения без thread_id → в первый диалог."""
    orphan = await session.execute(
        select(func.count(ChatMessage.id)).where(ChatMessage.thread_id.is_(None))
    )
    if int(orphan.scalar_one() or 0) == 0:
        return
    result = await session.execute(select(ChatThread).order_by(ChatThread.id).limit(1))
    thread = result.scalar_one_or_none()
    if thread is None:
        thread = ChatThread(title="Первый диалог")
        session.add(thread)
        await session.flush()
    await session.execute(
        update(ChatMessage).where(ChatMessage.thread_id.is_(None)).values(thread_id=thread.id)
    )
    await session.commit()
    logger.info("Миграция чата: сообщения привязаны к диалогу id=%s", thread.id)

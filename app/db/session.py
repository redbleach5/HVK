"""Асинхронная сессия SQLAlchemy и инициализация схемы."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models import AuthorProfile, Base

_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=False,
    future=True,
    connect_args={"timeout": 30},
)


@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _ensure_profile_desk_columns(conn) -> None:
    """Старые установки без миграций: недостающие поля профиля."""
    rows = (await conn.execute(text("PRAGMA table_info(author_profile)"))).all()
    have = {row[1] for row in rows}
    extra = {
        "desk": "ALTER TABLE author_profile ADD COLUMN desk VARCHAR(40) DEFAULT 'Чат'",
        "draft_text": "ALTER TABLE author_profile ADD COLUMN draft_text TEXT DEFAULT ''",
        "open_plan_item_id": "ALTER TABLE author_profile ADD COLUMN open_plan_item_id INTEGER",
    }
    for name, ddl in extra.items():
        if name not in have:
            await conn.execute(text(ddl))


async def _ensure_chat_threads(conn) -> None:
    """Миграция: chat_threads и thread_id у сообщений."""
    tables = {
        row[0]
        for row in (await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))).all()
    }
    if "chat_threads" not in tables:
        await conn.run_sync(lambda sync: Base.metadata.tables["chat_threads"].create(sync, checkfirst=True))

    rows = (await conn.execute(text("PRAGMA table_info(chat_messages)"))).all()
    have = {row[1] for row in rows}
    if "thread_id" not in have:
        await conn.execute(text("ALTER TABLE chat_messages ADD COLUMN thread_id INTEGER"))


async def init_db() -> None:
    """Создаёт таблицы и пустой профиль автора, если база только что появилась."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA busy_timeout=30000"))
        await _ensure_profile_desk_columns(conn)
        await _ensure_chat_threads(conn)

    async with SessionLocal() as session:
        from app.agents.chat_threads import migrate_orphan_messages

        await migrate_orphan_messages(session)
        existing = await session.get(AuthorProfile, 1)
        if existing is None:
            session.add(
                AuthorProfile(
                    id=1,
                    blog_name="Красивое в обычном",
                    about="",
                    onboarding_step=0,
                    onboarding_done=False,
                )
            )
            await session.commit()


async def get_session() -> AsyncIterator[AsyncSession]:
    """Зависимость FastAPI: выдаёт сессию и закрывает её после запроса."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

"""Асинхронная сессия SQLAlchemy и инициализация схемы."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models import AuthorProfile, Base

engine = create_async_engine(
    get_settings().database_url,
    echo=False,
    future=True,
)

SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Создаёт таблицы и пустой профиль автора, если база только что появилась."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
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
        yield session

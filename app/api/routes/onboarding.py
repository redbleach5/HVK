"""Онбординг: знакомство, импорт VK, профиль голоса."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, get_session
from app.llm.exceptions import EmptyArchiveError
from app.memory.ingest import reindex_posts, save_pasted_posts
from app.memory.store import MemoryStore
from app.schemas.api import ArchiveIn, OnboardingProfileIn, OnboardingStatus
from app.vk.client import import_wall_posts, is_configured
from app.voice.profile import build_voice_profile, voice_is_ready

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


async def _status(session: AsyncSession) -> OnboardingStatus:
    memory = MemoryStore(session)
    profile = await memory.get_profile()
    posts = await memory.count_posts()
    ready = await voice_is_ready(session)
    return OnboardingStatus(
        step=profile.onboarding_step,
        done=profile.onboarding_done,
        blog_name=profile.blog_name,
        about=profile.about or "",
        posts_imported=posts,
        voice_ready=ready,
    )


@router.get("/status", response_model=OnboardingStatus)
async def onboarding_status(session: AsyncSession = Depends(get_session)) -> OnboardingStatus:
    return await _status(session)


@router.post("/profile", response_model=OnboardingStatus)
async def save_profile(
    body: OnboardingProfileIn,
    session: AsyncSession = Depends(get_session),
) -> OnboardingStatus:
    """Шаг 1: название блога и пара слов о себе."""
    memory = MemoryStore(session)
    profile = await memory.get_profile()
    profile.blog_name = body.blog_name.strip()
    profile.about = body.about.strip()
    profile.onboarding_step = max(profile.onboarding_step, 1)
    await memory.log("onboarding", f"Познакомились: {profile.blog_name}")
    await session.commit()
    return await _status(session)


async def _build_voice_background(source: str) -> None:
    """Сбор голоса после ответа HTTP: клиент не ждёт LLM."""
    async with SessionLocal() as session:
        try:
            await build_voice_profile(session, source=source)
        except EmptyArchiveError:
            logger.info("Голос не собираю — архив пуст (source=%s)", source)
        except Exception:
            logger.exception("Не удалось собрать голос (source=%s)", source)


@router.post("/import-vk", response_model=OnboardingStatus)
async def import_vk(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> OnboardingStatus:
    """Шаг 2: импорт постов; голос собирается после ответа."""
    memory = MemoryStore(session)
    profile = await memory.get_profile()

    if is_configured():
        await import_wall_posts(session, with_comments=True)
        await reindex_posts(session)
    else:
        await memory.log(
            "onboarding",
            "VK пока не подключён — можно вставить свои посты вручную",
        )

    profile = await memory.get_profile()
    profile.onboarding_step = max(profile.onboarding_step, 2)
    await session.commit()
    background_tasks.add_task(_build_voice_background, "onboarding")
    return await _status(session)


@router.post("/skip-import", response_model=OnboardingStatus)
async def skip_import(session: AsyncSession = Depends(get_session)) -> OnboardingStatus:
    """Честный пропуск шага 2: без импорта VK и без построения голоса."""
    memory = MemoryStore(session)
    profile = await memory.get_profile()
    profile.onboarding_step = max(profile.onboarding_step, 2)
    await memory.log(
            "onboarding",
            "Пропустили импорт — голос появится, когда вставишь свои тексты",
        )
    await session.commit()
    return await _status(session)


@router.post("/archive", response_model=OnboardingStatus)
async def save_archive(
    body: ArchiveIn,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> OnboardingStatus:
    """Сохраняет посты сразу; голос собирается в фоне. Можно вызывать и после знакомства."""
    memory = MemoryStore(session)
    profile = await memory.get_profile()

    saved = await save_pasted_posts(session, body.posts)
    total = await memory.count_posts()
    if total < 2:
        raise HTTPException(
            status_code=400,
            detail="Нужно хотя бы два непустых поста — иначе голос будет выдумкой.",
        )

    await reindex_posts(session)
    await memory.log("onboarding", f"В архиве {total} постов (новых: {saved})")
    profile.onboarding_step = max(profile.onboarding_step, 2)
    await session.commit()
    if saved > 0:
        background_tasks.add_task(_build_voice_background, "paste")
    return await _status(session)


@router.post("/rebuild-voice", response_model=OnboardingStatus)
async def rebuild_voice(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> OnboardingStatus:
    """Повторно собирает голос, если архив уже есть. HTTP не ждёт LLM."""
    memory = MemoryStore(session)
    if await memory.count_posts() < 2:
        raise HTTPException(
            status_code=400,
            detail="Сначала нужны хотя бы два поста в архиве.",
        )
    await reindex_posts(session)
    await memory.log("onboarding", "Ещё раз собираю голос по архиву")
    await session.commit()
    background_tasks.add_task(_build_voice_background, "rebuild")
    return await _status(session)


@router.post("/complete", response_model=OnboardingStatus)
async def complete_onboarding(session: AsyncSession = Depends(get_session)) -> OnboardingStatus:
    """Шаг 3: короткий тур пройден. Без архива не закрываем — иначе начнётся угадайка."""
    memory = MemoryStore(session)
    if await memory.count_posts() < 2:
        raise HTTPException(
            status_code=400,
            detail="Сначала вставь хотя бы два своих поста — иначе я буду угадывать.",
        )
    profile = await memory.get_profile()
    profile.onboarding_step = 3
    profile.onboarding_done = True
    await memory.log("onboarding", "Онбординг завершён — можно заглянуть на «Сегодня»")
    await session.commit()
    return await _status(session)

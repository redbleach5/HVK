"""Онбординг: знакомство, импорт VK, профиль голоса."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.memory.store import MemoryStore
from app.schemas.api import OnboardingProfileIn, OnboardingStatus
from app.vk.client import import_wall_posts, is_configured
from app.voice.profile import build_voice_profile, voice_is_ready

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


@router.post("/import-vk", response_model=OnboardingStatus)
async def import_vk(session: AsyncSession = Depends(get_session)) -> OnboardingStatus:
    """Шаг 2: импорт постов и построение голоса."""
    memory = MemoryStore(session)
    profile = await memory.get_profile()

    if is_configured():
        await import_wall_posts(session, count=60, with_comments=True)
    else:
        await memory.log(
            "onboarding",
            "VK пока не подключён — можно продолжить без импорта и добавить позже",
        )

    await build_voice_profile(session, source="onboarding")
    profile = await memory.get_profile()
    profile.onboarding_step = max(profile.onboarding_step, 2)
    await session.commit()
    return await _status(session)


@router.post("/skip-import", response_model=OnboardingStatus)
async def skip_import(session: AsyncSession = Depends(get_session)) -> OnboardingStatus:
    """Честный пропуск шага 2: без импорта VK и без построения голоса."""
    memory = MemoryStore(session)
    profile = await memory.get_profile()
    profile.onboarding_step = max(profile.onboarding_step, 2)
    await memory.log(
        "onboarding",
        "Пропустили импорт — голос соберём позже, когда подключим VK",
    )
    await session.commit()
    return await _status(session)


@router.post("/complete", response_model=OnboardingStatus)
async def complete_onboarding(session: AsyncSession = Depends(get_session)) -> OnboardingStatus:
    """Шаг 3: короткий тур пройден."""
    memory = MemoryStore(session)
    profile = await memory.get_profile()
    profile.onboarding_step = 3
    profile.onboarding_done = True
    await memory.log("onboarding", "Онбординг завершён — можно заглянуть на «Сегодня»")
    await session.commit()
    return await _status(session)

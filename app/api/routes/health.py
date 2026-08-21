"""Health-check сервисов."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.llm.client import get_llm
from app.schemas.common import HealthStatus
from app.vk.client import is_configured

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus)
async def health() -> HealthStatus:
    """Проверяет мозг, глаза и наличие токенов."""
    settings = get_settings()
    llm = get_llm()
    brain = await llm.ping_brain()
    eyes = await llm.ping_eyes()
    vk_ok = is_configured()
    tg_ok = bool(settings.telegram_bot_token)

    if brain and eyes:
        message = "Модели доступны"
    elif not brain and not eyes:
        message = "Модели недоступны (brain :8000, eyes :8001)"
    elif not brain:
        message = "Текстовая модель недоступна (:8000)"
    else:
        message = "Фото-модель недоступна (:8001)"

    return HealthStatus(
        ok=brain or eyes,
        brain=brain,
        eyes=eyes,
        vk_configured=vk_ok,
        telegram_configured=tg_ok,
        message=message,
    )

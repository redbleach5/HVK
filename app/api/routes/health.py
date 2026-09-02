"""Health-check сервисов."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.diagnostics.engine import last_report, run_diagnostics
from app.llm.client import get_llm
from app.schemas.common import DiagnosticsOut, HealthStatus
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
        message = "Модели недоступны"
    elif not brain:
        message = "Текстовая модель недоступна"
    else:
        message = "Фото-модель недоступна"

    return HealthStatus(
        ok=brain,
        brain=brain,
        eyes=eyes,
        vk_configured=vk_ok,
        telegram_configured=tg_ok,
        message=message,
    )


@router.get("/health/diagnostics", response_model=DiagnosticsOut)
async def health_diagnostics(
    session: AsyncSession = Depends(get_session),
    *,
    probe: bool = True,
    insight: bool = True,
    refresh: bool = True,
) -> DiagnosticsOut:
    """Самодиагностика: метрики, пробы, подсказка для автора."""
    if not refresh:
        cached = last_report()
        if cached:
            return DiagnosticsOut(**cached)
    return await run_diagnostics(session, probe=probe, insight=insight)

"""Общие зависимости и обработчики ошибок API."""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.llm.exceptions import EmptyArchiveError, LlmResponseError, ModelAsleepError
from app.vk.client import (
    VkConfirmRequiredError,
    VkMessagesUnavailableError,
    VkNotConfiguredError,
    VkWallUnavailableError,
)


async def model_asleep_handler(_: Request, exc: ModelAsleepError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": exc.user_message})


async def llm_response_handler(_: Request, exc: LlmResponseError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": exc.user_message})


async def empty_archive_handler(_: Request, exc: EmptyArchiveError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": exc.user_message})


async def vk_not_configured_handler(_: Request, exc: VkNotConfiguredError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": exc.user_message})


async def vk_confirm_handler(_: Request, exc: VkConfirmRequiredError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": exc.user_message})


async def vk_messages_handler(_: Request, exc: VkMessagesUnavailableError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": exc.user_message})


async def vk_wall_handler(_: Request, exc: VkWallUnavailableError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": exc.user_message})


async def sqlite_locked_handler(_: Request, exc: OperationalError) -> JSONResponse:
    msg = str(exc.orig) if getattr(exc, "orig", None) else str(exc)
    if "locked" not in msg.lower() and "busy" not in msg.lower():
        return JSONResponse(status_code=500, content={"detail": "Что-то тихо не сложилось. Попробуй ещё раз."})
    return JSONResponse(
        status_code=503,
        content={"detail": "Сейчас занято — напиши ещё раз через пару секунд."},
    )


def not_found(message: str = "Не нашла") -> HTTPException:
    return HTTPException(status_code=404, detail=message)

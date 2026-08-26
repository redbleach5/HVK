"""Точка входа FastAPI «Тихая редакция»."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import (
    empty_archive_handler,
    llm_response_handler,
    model_asleep_handler,
    sqlite_locked_handler,
    vk_confirm_handler,
    vk_messages_handler,
    vk_not_configured_handler,
    vk_wall_handler,
)
from app.api.routes import chat, health, ideas_plan, misc, onboarding, photo, text, today
from app.config import get_settings
from app.db.session import init_db
from app.llm.exceptions import EmptyArchiveError, LlmResponseError, ModelAsleepError
from app.logging_setup import setup_logging
from app.scheduler.jobs import start_scheduler, stop_scheduler
from app.vk.client import (
    VkConfirmRequiredError,
    VkMessagesUnavailableError,
    VkNotConfiguredError,
    VkWallUnavailableError,
)
from sqlalchemy.exc import OperationalError


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Старт: каталоги, БД, планировщик. Стоп: планировщик."""
    setup_logging()
    settings = get_settings()
    settings.ensure_directories()
    await init_db()
    start_scheduler()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    """Собирает приложение со всеми роутами и обработчиками ошибок."""
    settings = get_settings()
    application = FastAPI(title=settings.app_title, lifespan=lifespan)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.add_exception_handler(ModelAsleepError, model_asleep_handler)
    application.add_exception_handler(LlmResponseError, llm_response_handler)
    application.add_exception_handler(EmptyArchiveError, empty_archive_handler)
    application.add_exception_handler(VkNotConfiguredError, vk_not_configured_handler)
    application.add_exception_handler(VkConfirmRequiredError, vk_confirm_handler)
    application.add_exception_handler(VkMessagesUnavailableError, vk_messages_handler)
    application.add_exception_handler(VkWallUnavailableError, vk_wall_handler)
    application.add_exception_handler(OperationalError, sqlite_locked_handler)

    application.include_router(health.router)
    application.include_router(onboarding.router)
    application.include_router(today.router)
    application.include_router(photo.router)
    application.include_router(text.router)
    application.include_router(ideas_plan.router)
    application.include_router(misc.router)
    application.include_router(chat.router)

    return application


app = create_app()

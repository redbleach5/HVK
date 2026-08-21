"""Telegram-бот — мобильное продолжение дашборда через тот же API."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

from app.config import get_settings
from app.logging_setup import setup_logging

logger = logging.getLogger(__name__)

API_BASE = os.environ.get("HVK_API_BASE", "http://127.0.0.1:8080")


def _api() -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=300.0)


def _get(path: str, **params):
    with _api() as client:
        r = client.get(path, params=params)
        r.raise_for_status()
        return r.json()


def _post(path: str, json: dict | None = None, files=None):
    with _api() as client:
        if files:
            r = client.post(path, files=files)
        else:
            r = client.post(path, json=json or {})
        r.raise_for_status()
        return r.json()


def _err(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            detail = exc.response.json().get("detail")
            if detail:
                return str(detail)
        except Exception:
            pass
        if exc.response.status_code == 503:
            return "Модель ещё просыпается, подожди минутку 🤍"
    if isinstance(exc, httpx.ConnectError):
        return "Сервер редакции ещё не проснулся 🤍"
    return "Не получилось аккуратно. Загляни чуть позже 🤍"


def create_dispatcher() -> Dispatcher:
    """Собирает обработчики бота."""
    dp = Dispatcher()

    @dp.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        await message.answer(
            "Привет 🤍 Я тихая редакция в кармане.\n\n"
            "Пришли фото — разберу.\n"
            "Текст от 50 символов — мягко отредактирую.\n"
            "/today — утреннее резюме\n"
            "/ideas — три идеи\n"
            "/stats — мини-отчёт недели\n\n"
            "Сама ничего не публикую и не решаю за тебя."
        )

    @dp.message(Command("today"))
    async def cmd_today(message: Message) -> None:
        try:
            data = _get("/today")
        except Exception as exc:
            await message.answer(_err(exc))
            return
        lines = [data.get("digest") or "Пока тихо."]
        for idea in (data.get("ideas") or [])[:3]:
            lines.append(f"\n· {idea.get('theme')}: {idea.get('why_now') or ''}")
        for rem in (data.get("plan_reminders") or [])[:3]:
            lines.append(f"\nплан: {rem}")
        await message.answer("\n".join(lines)[:4000])

    @dp.message(Command("ideas"))
    async def cmd_ideas(message: Message) -> None:
        try:
            batch = _post("/ideas/generate", json={"count": 3})
        except Exception as exc:
            await message.answer(_err(exc))
            return
        parts = []
        for idea in batch.get("ideas") or []:
            why = (idea.get("why") or {}).get("summary") or idea.get("why_now") or ""
            parts.append(
                f"*{idea.get('theme')}*\n"
                f"{idea.get('description') or ''}\n"
                f"почему: {why}"
            )
        await message.answer("\n\n".join(parts)[:4000] or "Идей пока нет")

    @dp.message(Command("stats"))
    async def cmd_stats(message: Message) -> None:
        try:
            data = _get("/analytics", with_report=False)
        except Exception as exc:
            await message.answer(_err(exc))
            return
        tops = data.get("top_posts") or []
        lines = [f"В архиве {data.get('posts_count', 0)} постов."]
        for p in tops[:5]:
            lines.append(
                f"· {p.get('theme') or 'пост'} — eng {p.get('engagement', 0):.0f}"
            )
        await message.answer("\n".join(lines)[:4000])

    @dp.message(F.photo)
    async def on_photo(message: Message, bot: Bot) -> None:
        photo = message.photo[-1]
        try:
            file = await bot.get_file(photo.file_id)
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                path = Path(tmp.name)
            await bot.download_file(file.file_path, destination=path)
            with path.open("rb") as fh:
                result = _post(
                    "/photo/analyze",
                    files=[("files", (path.name, fh, "image/jpeg"))],
                )
            path.unlink(missing_ok=True)
        except Exception as exc:
            await message.answer(_err(exc))
            return

        advice = (result.get("advice") or ["—"])[0]
        text = (
            f"{result.get('verdict') or 'Вердикт'}\n\n"
            f"Главный совет: {advice}\n\n"
            f"Подпись: {result.get('caption_direction') or '—'}"
        )
        await message.answer(text[:4000])

    @dp.message(F.text)
    async def on_text(message: Message) -> None:
        text = (message.text or "").strip()
        if text.startswith("/"):
            return
        if len(text) < 50:
            await message.answer(
                "Если это черновик — пришли от 50 символов, "
                "и я мягко отредактирую 🤍"
            )
            return
        try:
            result = _post("/text/edit", json={"draft": text, "topic_hint": ""})
        except Exception as exc:
            await message.answer(_err(exc))
            return
        voice = "в голосе" if result.get("in_voice") else "чуть выбивается"
        reply = (
            f"Готово ({voice}):\n\n"
            f"{result.get('revised_text') or ''}\n\n"
            f"{result.get('voice_notes') or ''}"
        )
        await message.answer(reply[:4000])

    return dp


async def main() -> None:
    setup_logging()
    settings = get_settings()
    token = settings.telegram_bot_token
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан в .env")
    bot = Bot(token=token)
    dp = create_dispatcher()
    logger.info("Telegram-бот запускается")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

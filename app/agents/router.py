"""Маршрутизация интентов чата.

Автор работает в диалоге. Инструмент срабатывает только на явную команду
(«идеи», «план», «поправь …»). Обычная фраза с этими словами — разговор,
не генератор и не выгрузка плана.

Слои:
1. Эвристика — мгновенно, без сети. None = живой чат.
2. Не команда — сразу general, без второго вызова модели.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.api import ChatOut


_EDIT_PREFIXES = ("поправь", "отредактируй", "редактура", "поправь текст")
_TO_PLAN_PREFIXES = ("в план", "добавь в план")
_CONCIERGE_MARKERS = ("ответь на", "черновик ответа", "это лс", "личное сообщение")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def classify_intent_heuristic(message: str, *, has_photos: bool) -> Optional[str]:
    """Явная команда → инструмент. Иначе None: это диалог, не угадайка."""
    if has_photos:
        return "photo"
    t = _norm(message)
    if not t:
        return "help"
    if t in {"помощь", "help", "?", "/help"} or t.startswith("что умеешь"):
        return "help"
    if t.startswith("/today") or t in {"сегодня", "сводка", "дайджест"}:
        return "today"
    if t.startswith("/ideas") or t in {"идеи", "идея"} or t.startswith("предложи идеи"):
        return "ideas"
    if t.startswith("/stats") or t in {"аналитика", "статистика", "стата"}:
        return "analytics"
    if t in {"план", "что в плане"} or t.startswith("/plan"):
        return "plan"
    if t in {"сезон", "сезонные", "из архива"} or t.startswith("/seasonal"):
        return "seasonal"
    if t in {"входящие", "inbox", "лс список", "лс"}:
        return "inbox"
    if t.startswith("опубликовать") or t.startswith("/publish"):
        return "publish"
    if t.startswith(_TO_PLAN_PREFIXES):
        return "to_plan"
    if any(t.startswith(m) for m in _CONCIERGE_MARKERS):
        return "concierge"
    if any(t.startswith(p) for p in _EDIT_PREFIXES) or t.startswith("черновик"):
        return "edit"
    return None


# --- Извлечение текста из сообщения для конкретных интентов ---

_PUBLISH_RE = re.compile(
    r"опубликовать(?:\s+в\s+vk)?\s*:?\s*(.*)$",
    flags=re.I | re.S,
)
_TO_PLAN_RE = re.compile(
    r"^(в план|добавь в план)\s*:?\s*",
    flags=re.I,
)


def extract_publish_text(message: str) -> tuple[str, bool]:
    """Возвращает (текст после маркера, подтверждено ли).

    Слово «подтверждаю» вырезается из тела поста, но учитывается как подтверждение.
    """
    text = message.strip()
    confirm = "подтверждаю" in _norm(text)
    m = _PUBLISH_RE.search(text)
    body = m.group(1).strip() if m else text
    if confirm:
        # Убираем «подтверждаю» из тела поста, чтобы не попало в VK
        body = re.sub(r"\bподтверждаю\b", "", body, flags=re.I).strip()
        body = re.sub(r"\s{2,}", " ", body).strip()
    return body, confirm


def extract_plan_title(message: str) -> str:
    """Заголовок для пункта плана из сообщения «в план: …»."""
    return _TO_PLAN_RE.sub("", message.strip(), count=1).strip() or message.strip()


def extract_concierge_text(message: str) -> str:
    """Убирает служебные префиксы для консьержа."""
    return re.sub(
        r"^(ответь на|черновик ответа|это лс|личное сообщение)\s*:?\s*",
        "",
        message.strip(),
        flags=re.I,
    ).strip()


# --- Главная точка входа ---

@dataclass
class IntentDecision:
    """Решение маршрутизатора: интент + распарсенные поля."""

    intent: str
    draft_text: str = ""
    publish_text: str = ""
    plan_title: str = ""
    confirm_publish: bool = False
    source: str = "heuristic"


async def classify_intent(
    session: AsyncSession,
    message: str,
    *,
    has_photos: bool,
) -> IntentDecision:
    """Команда → инструмент, иначе general. Без второго вызова модели."""
    guessed = classify_intent_heuristic(message, has_photos=has_photos)
    if guessed and guessed != "general":
        out = IntentDecision(intent=guessed, source="heuristic")
        if guessed == "edit":
            out.draft_text = message.strip()
        elif guessed == "publish":
            text, confirm = extract_publish_text(message)
            out.publish_text = text
            out.confirm_publish = confirm
        elif guessed == "to_plan":
            out.plan_title = extract_plan_title(message)
        return out

    # Не команда — диалог. Второй вызов модели здесь только крадёт время.
    return IntentDecision(intent="general", source="heuristic")


# --- Таблица маршрутов ---

# Тип обработчика: async(session, message, paths, history, decision) -> ChatOut
IntentHandler = Callable[
    ["AsyncSession", str, "list", list, IntentDecision],
    "Awaitable[ChatOut]",
]


# Заполняется в `agents/chat.py` через register_handler(), чтобы избежать циклического импорта.
_HANDLERS: dict[str, IntentHandler] = {}


def register_handler(intent: str) -> Callable[[IntentHandler], IntentHandler]:
    """Декоратор регистрации обработчика интента."""

    def _wrap(fn: IntentHandler) -> IntentHandler:
        _HANDLERS[intent] = fn
        return fn

    return _wrap


def get_handler(intent: str) -> Optional[IntentHandler]:
    return _HANDLERS.get(intent)


def list_routes() -> dict[str, str]:
    """Диагностика: какие интенты и где зарегистрированы."""
    return {intent: fn.__module__ + "." + fn.__name__ for intent, fn in _HANDLERS.items()}

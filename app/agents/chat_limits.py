"""Лимиты сообщений чата: приём, хранение, промпт."""

from __future__ import annotations

import logging
import re

from app.config import get_settings

logger = logging.getLogger(__name__)

_CLIP_NOTE = "\n… (текст сокращён — слишком длинный для одного сообщения)"

_SKIP_SEARCH = frozenset(
    {
        "привет",
        "здравствуй",
        "здравствуйте",
        "добрый день",
        "доброе утро",
        "добрый вечер",
        "спасибо",
        "пока",
        "ок",
        "окей",
        "хорошо",
        "да",
        "нет",
        "угу",
        "ага",
        "поняла",
        "понял",
        "ясно",
        "как дела",
        "ты тут",
    }
)

_URL_RE = re.compile(r"https?://[^\s<>]+|t\.me/[^\s<>]+", re.I)

_SEARCH_HINTS = (
    "погугли",
    "загугли",
    "найди в интернете",
    "поищи в интернете",
    "посмотри в интернете",
    "в интернете",
    "в сети",
    "свежие новости",
    "новости",
    "погода",
    "курс валют",
    "сколько стоит",
    "актуальн",
    "что происходит",
    "что случилось",
    "сейчас в мире",
    "кто такой",
    "кто такая",
    "когда будет",
    "официальн",
    "википед",
    "wikipedia",
    "гугл",
    "google",
    "найди ",
    "найти ",
    "поищи ",
    "телеграм",
    "telegram",
    "t.me",
)

_ARCHIVE_HINTS = (
    "мой архив",
    "мои тексты",
    "мой пост",
    "мой голос",
    "как я пишу",
    "из архива",
    "мои посты",
)

_EDITORIAL_HINTS = (
    "выложить",
    "постить",
    "черновик",
    "кадр",
    "как думаешь",
    "что лучше",
)


def chat_message_max_chars() -> int:
    return max(4000, int(get_settings().chat_message_max_chars))


def prepare_chat_message(text: str) -> str:
    """Нормализует и обрезает входящий текст. Не падает на гигантском paste."""
    raw = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    limit = chat_message_max_chars()
    if len(raw) <= limit:
        return raw
    clipped = raw[:limit].rstrip() + _CLIP_NOTE
    logger.warning("chat message clipped from %s to %s chars", len(raw), len(clipped))
    return clipped


def web_search_query(message: str, *, max_chars: int = 480) -> str:
    """Короткий запрос для поиска — ссылка и суть, не весь роман."""
    raw = message or ""
    urls = _URL_RE.findall(raw)
    text = " ".join(raw.split())
    if urls:
        rest = _URL_RE.sub(" ", text)
        rest = " ".join(rest.split())
        text = f"{urls[0]} {rest}".strip() if rest else urls[0]
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip()


def _capability_only(t: str) -> bool:
    """«Ты умеешь интернет?» — не запрос. «Найди блог X» — запрос."""
    if any(x in t for x in ("блог", "телеграм", "telegram", "t.me", "новост", "погод")):
        return False
    return bool(re.search(r"(можешь|умеешь).{0,48}(интернет|в сети)", t))


def needs_web_search(message: str) -> bool:
    """Искать в сети, если нужны факты, ссылка или чужой блог. Привет и архив — нет."""
    raw = message or ""
    t = re.sub(r"\s+", " ", raw.strip().lower())
    if not t or t in _SKIP_SEARCH:
        return False
    if len(t) < 8:
        return False
    if _URL_RE.search(raw):
        return True
    if _capability_only(t):
        return False
    if any(h in t for h in _SEARCH_HINTS):
        return True
    if any(h in t for h in _ARCHIVE_HINTS):
        return False
    if "?" not in raw or len(t) < 20:
        return False
    if any(h in t for h in _EDITORIAL_HINTS):
        return False
    return True

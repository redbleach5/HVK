"""HTTP-клиент дашборда к FastAPI на :8080."""

from __future__ import annotations

import json
import os
from typing import Any, Iterator

import httpx
import streamlit as st

API_BASE = os.environ.get("HVK_API_BASE", "http://127.0.0.1:8080")


class ApiError(Exception):
    """Ошибка API с человеческим текстом."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _timeout_call() -> httpx.Timeout:
    # Одноразовые запросы (идеи, фото, редактура): модель может думать долго.
    return httpx.Timeout(1200.0, connect=20.0)


def _timeout_stream() -> httpx.Timeout:
    # Живой чат: не резать по сумме минут, только если связь совсем молчит.
    return httpx.Timeout(connect=20.0, read=None, write=120.0, pool=20.0)


def _client(timeout: httpx.Timeout | float | None = None) -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=timeout or _timeout_call())


def api_get(path: str, *, timeout: httpx.Timeout | float | None = None, **params: Any) -> Any:
    with _client(timeout=timeout) as client:
        response = client.get(path, params={k: v for k, v in params.items() if v is not None})
    return _handle(response)


def api_post(path: str, json: dict | None = None, files: list | None = None) -> Any:
    with _client() as client:
        if files:
            response = client.post(path, files=files)
        else:
            response = client.post(path, json=json or {})
    return _handle(response)


def api_post_form(
    path: str,
    data: dict[str, Any],
    files: list | None = None,
) -> Any:
    """POST multipart/form-data (публикация с фото)."""
    with _client() as client:
        response = client.post(path, data=data, files=files or None)
    return _handle(response)


def iter_chat_stream(message: str) -> Iterator[dict[str, Any]]:
    """NDJSON с /chat/stream: thinking, text, done."""
    with _client(timeout=_timeout_stream()) as client:
        with client.stream("POST", "/chat/stream", data={"message": message}) as response:
            if response.status_code >= 400:
                response.read()
                _handle(response)
            for line in response.iter_lines():
                if not line:
                    continue
                yield json.loads(line)


def api_patch(path: str, json: dict, *, timeout: httpx.Timeout | float | None = None) -> Any:
    with _client(timeout=timeout) as client:
        response = client.patch(path, json=json)
    return _handle(response)


def api_delete(path: str) -> Any:
    with _client() as client:
        response = client.delete(path)
    return _handle(response)


def _author_detail(detail: object) -> str:
    """Текст для автора: без стеков, портов и служебных слов."""
    if isinstance(detail, list):
        return "Что-то тихо не сложилось. Попробуй ещё раз."
    text = str(detail or "").strip()
    if not text:
        return "Что-то тихо не сложилось. Попробуй ещё раз."
    low = text.lower()
    if (
        text.startswith("{")
        or text.startswith("[")
        or "traceback" in low
        or ".env" in low
        or "ollama" in low
        or "gguf" in low
        or "llama.cpp" in low
        or "127.0.0.1" in low
        or "localhost:" in low
    ):
        return "Что-то тихо не сложилось. Попробуй ещё раз."
    return text


def _handle(response: httpx.Response) -> Any:
    if response.status_code >= 400:
        detail: object = "Что-то тихо не сложилось"
        try:
            payload = response.json()
            detail = payload.get("detail") or detail
        except Exception:
            detail = response.text or detail
        raise ApiError(_author_detail(detail), response.status_code)
    if response.status_code == 204 or not response.content:
        return {}
    return response.json()


def vk_is_configured() -> bool:
    """Как API: группа или ключ стены + owner."""
    try:
        from app.vk.client import is_configured

        return is_configured()
    except Exception:
        return False


def friendly_error(exc: Exception) -> None:
    """Показывает ошибку в интерфейсе."""
    if isinstance(exc, ApiError):
        st.warning(exc.message)
    elif isinstance(exc, httpx.ConnectError):
        st.warning("Редакция сейчас молчит. Загляни чуть позже.")
    else:
        st.warning("Что-то тихо не сложилось. Попробуй ещё раз.")

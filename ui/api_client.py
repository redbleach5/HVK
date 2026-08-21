"""HTTP-клиент дашборда к FastAPI на :8080."""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx
import streamlit as st

API_BASE = os.environ.get("HVK_API_BASE", "http://127.0.0.1:8080")


class ApiError(Exception):
    """Ошибка API с человеческим текстом."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _client(timeout: float = 300.0) -> httpx.Client:
    return httpx.Client(base_url=API_BASE, timeout=timeout)


def api_get(path: str, **params: Any) -> Any:
    with _client() as client:
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


def api_patch(path: str, json: dict) -> Any:
    with _client() as client:
        response = client.patch(path, json=json)
    return _handle(response)


def api_delete(path: str) -> Any:
    with _client() as client:
        response = client.delete(path)
    return _handle(response)


def _handle(response: httpx.Response) -> Any:
    if response.status_code >= 400:
        detail = "Что-то тихо не сложилось"
        try:
            payload = response.json()
            detail = payload.get("detail") or detail
        except Exception:
            detail = response.text or detail
        raise ApiError(str(detail), response.status_code)
    if response.status_code == 204 or not response.content:
        return {}
    return response.json()


def friendly_error(exc: Exception) -> None:
    """Показывает ошибку в интерфейсе."""
    if isinstance(exc, ApiError):
        st.warning(exc.message)
    elif isinstance(exc, httpx.ConnectError):
        st.warning("API не запущен (порт 8080).")
    else:
        st.warning("Ошибка запроса. Попробуй ещё раз.")

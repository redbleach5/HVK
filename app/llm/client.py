"""Клиент к двум llama-server: мозг (текст) и глаза (фото)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, OpenAIError
from pydantic import BaseModel, ValidationError
import httpx

from app.config import get_settings
from app.llm.exceptions import LlmResponseError, ModelAsleepError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)

_COT_MARKERS = (
    "thinking process",
    "here's a thinking",
    "let's analyze",
    "step 1:",
    "анализ пользовательского",
    "процесс мышления",
    "reasoning:",
    "<think>",
    "</think>",
)


def strip_cot(text: str) -> str:
    """Убирает просочившийся ход мыслей; пустая строка = ответа нет."""
    text = (text or "").strip()
    if not text:
        return ""
    # Блоки <think>…</think>
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
    low = text.lower()
    for marker in _COT_MARKERS:
        idx = low.find(marker)
        if idx == -1:
            continue
        before = text[:idx].strip()
        if before and len(before) >= 24 and marker not in before.lower():
            return before
        # Весь ответ — рассуждение: для автора это мусор
        return ""
    return text


def _as_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        inner = value.get("content") or value.get("text")
        if isinstance(inner, str):
            return inner
    return ""


def _message_thinking(message: object) -> str:
    for name in ("thinking", "reasoning_content", "reasoning"):
        text = _as_text(getattr(message, name, None)).strip()
        if text:
            return text
    extra = getattr(message, "model_extra", None)
    if isinstance(extra, dict):
        for name in ("thinking", "reasoning_content", "reasoning"):
            text = _as_text(extra.get(name)).strip()
            if text:
                return text
    return ""


def _delta_piece(delta: object, *names: str) -> str:
    for name in names:
        text = _as_text(getattr(delta, name, None))
        if text:
            return text
    extra = getattr(delta, "model_extra", None)
    if isinstance(extra, dict):
        for name in names:
            text = _as_text(extra.get(name))
            if text:
                return text
    return ""


def _ollama_chat_url(openai_base: str) -> str:
    root = (openai_base or "").rstrip("/")
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    return f"{root}/api/chat"


class LlmClient:
    """Обёртка над OpenAI SDK для двух локальных серверов llama.cpp."""

    def __init__(self) -> None:
        settings = get_settings()
        self._brain = AsyncOpenAI(
            base_url=settings.brain_base_url,
            api_key="not-needed",
            timeout=settings.llm_timeout,
        )
        self._eyes = AsyncOpenAI(
            base_url=settings.eyes_base_url,
            api_key="not-needed",
            timeout=settings.vision_timeout,
        )
        self._brain_model = settings.brain_model
        self._eyes_model = settings.eyes_model
        self._brain_chat_url = _ollama_chat_url(settings.brain_base_url)
        self._llm_timeout = settings.llm_timeout

    async def complete(
        self,
        *,
        system: str,
        user: str,
        images: list[str] | None = None,
        temperature: float = 0.4,
        max_tokens: int = 2500,
        no_reasoning: bool = False,
        json_object: bool = False,
    ) -> str:
        """Обычный текстовый (или vision) ответ. images — data-url или base64 jpeg/png.

        no_reasoning=True — не подставлять внутренний «поток размышлений»
        модели вместо ответа: для автора это выглядит как чужие мысли.
        """
        client = self._eyes if images else self._brain
        model = self._eyes_model if images else self._brain_model
        content: str | list[dict[str, Any]]
        if images:
            parts: list[dict[str, Any]] = [{"type": "text", "text": user}]
            for image in images:
                url = image if image.startswith("data:") else f"data:image/jpeg;base64,{image}"
                parts.append({"type": "image_url", "image_url": {"url": url}})
            content = parts
        else:
            content = user

        try:
            response = await client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                extra_body={
                    "think": False,
                    **({"format": "json"} if json_object else {}),
                },
            )
        except (APIConnectionError, APITimeoutError) as exc:
            logger.warning("Модель недоступна: %s", exc)
            raise ModelAsleepError(str(exc)) from exc
        except OpenAIError as exc:
            logger.exception("Ошибка llama-server")
            raise ModelAsleepError(str(exc)) from exc

        message = response.choices[0].message
        text = (message.content or "").strip()
        if no_reasoning:
            text = strip_cot(text)
        if not text:
            raise LlmResponseError("пустой ответ модели")
        return text

    def _thought_payload(
        self,
        *,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> dict[str, Any]:
        return {
            "model": self._brain_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": stream,
            "think": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

    async def complete_thoughtful(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.4,
        max_tokens: int = 4000,
    ) -> tuple[str, str]:
        """Ответ + отдельный ход мысли. Мысль не смешивается с репликой."""
        timeout = httpx.Timeout(self._llm_timeout, connect=20.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self._brain_chat_url,
                    json=self._thought_payload(
                        system=system,
                        user=user,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=False,
                    ),
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.warning("Модель недоступна: %s", exc)
            raise ModelAsleepError(str(exc)) from exc

        message = data.get("message") or {}
        text = strip_cot(_as_text(message.get("content")).strip())
        thinking = _as_text(message.get("thinking")).strip()
        if not text:
            raise LlmResponseError("пустой ответ модели")
        return text, thinking

    async def stream_thoughtful(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.4,
        max_tokens: int = 4000,
    ):
        """Стримит ход мысли, затем реплику. Yield: ('thinking'|'text', delta)."""
        # Стрим: ждать следующий кусок сколько нужно. Обрывать по «прошло N секунд всего» нельзя.
        timeout = httpx.Timeout(connect=20.0, read=None, write=120.0, pool=20.0)
        payload = self._thought_payload(
            system=system,
            user=user,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", self._brain_chat_url, json=payload) as response:
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        logger.warning("Модель недоступна: %s", exc)
                        raise ModelAsleepError(str(exc)) from exc
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        message = chunk.get("message") or {}
                        thought = _as_text(message.get("thinking"))
                        if thought:
                            yield ("thinking", thought)
                        piece = _as_text(message.get("content"))
                        if piece:
                            yield ("text", piece)
        except ModelAsleepError:
            raise
        except httpx.HTTPError as exc:
            logger.warning("Модель недоступна: %s", exc)
            raise ModelAsleepError(str(exc)) from exc

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        images: list[str] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2500,
        no_reasoning: bool = False,
    ) -> T:
        """Просит модель ответить JSON и валидирует его схемой Pydantic.

        Повторяет запрос один раз, если первый ответ не разбирается.
        """
        if images:
            json_system = (
                f"{system}\n\n"
                "Ответь одним JSON-объектом, без markdown и без текста вокруг. "
                "Русский язык. Короткие человеческие формулировки."
            )
        else:
            json_system = (
                f"{system}\n\n"
                "Ответь СТРОГО одним JSON-объектом без пояснений вокруг. "
                "Не используй markdown-ограждения, если можешь обойтись без них. "
                f"Структура должна соответствовать этой JSON Schema:\n"
                f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}"
            )
        last_error: Exception | None = None
        for attempt in range(2):
            raw = await self.complete(
                system=json_system,
                user=user if attempt == 0 else (
                    user + "\n\nПредыдущий ответ был невалидным JSON. Верни только корректный JSON."
                ),
                images=images,
                temperature=temperature if attempt == 0 else 0.1,
                max_tokens=max_tokens,
                no_reasoning=True,
                json_object=not bool(images),
            )
            try:
                data = _extract_json(raw)
                return schema.model_validate(data)
            except (ValueError, ValidationError) as exc:
                last_error = exc
                logger.info(
                    "Не удалось разобрать JSON (попытка %s): %s | raw=%s",
                    attempt + 1,
                    exc,
                    (raw or "")[:500].replace("\n", " "),
                )
        raise LlmResponseError(str(last_error)) from last_error

    async def ping_brain(self) -> bool:
        """Проверяет, отвечает ли текстовый сервер. Короткий таймаут — не ждать мёртвый хост."""
        return await self._ping_url(self._brain.base_url)

    async def ping_eyes(self) -> bool:
        """Проверяет, отвечает ли vision-сервер. Короткий таймаут — не ждать 7700 XT."""
        return await self._ping_url(self._eyes.base_url)

    async def _ping_url(self, base_url: object) -> bool:
        url = str(base_url).rstrip("/") + "/models"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url)
            return response.status_code < 500
        except Exception:
            logger.debug("Пинг модели не удался: %s", url, exc_info=True)
            return False


def _extract_json(text: str) -> Any:
    """Достаёт JSON-объект из ответа; если склеено несколько — берёт тот, где есть смысл."""
    text = text.strip()
    fence = _JSON_FENCE.search(text)
    if fence:
        text = fence.group(1).strip()
    decoder = json.JSONDecoder()
    found: list[Any] = []
    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start < 0:
            break
        try:
            obj, consumed = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            i = start + 1
            continue
        if isinstance(obj, dict):
            found.append(obj)
        i = start + max(consumed, 1)
    if not found:
        raise ValueError("в ответе нет JSON-объекта")
    for obj in found:
        if any(k in obj for k in ("verdict", "why", "caption_direction", "advice")):
            return obj
    return found[0]


_client: LlmClient | None = None


def get_llm() -> LlmClient:
    """Возвращает общий клиент LLM."""
    global _client
    if _client is None:
        _client = LlmClient()
    return _client

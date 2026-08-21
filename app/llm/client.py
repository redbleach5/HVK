"""Клиент к двум llama-server: мозг (текст) и глаза (фото)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, OpenAIError
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.llm.exceptions import LlmResponseError, ModelAsleepError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


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

    async def complete(
        self,
        *,
        system: str,
        user: str,
        images: list[str] | None = None,
        temperature: float = 0.4,
        max_tokens: int = 2500,
    ) -> str:
        """Обычный текстовый (или vision) ответ. images — data-url или base64 jpeg/png."""
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
            )
        except (APIConnectionError, APITimeoutError) as exc:
            logger.warning("Модель недоступна: %s", exc)
            raise ModelAsleepError(str(exc)) from exc
        except OpenAIError as exc:
            logger.exception("Ошибка llama-server")
            raise ModelAsleepError(str(exc)) from exc

        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise LlmResponseError("пустой ответ модели")
        return text

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        images: list[str] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2500,
    ) -> T:
        """Просит модель ответить JSON и валидирует его схемой Pydantic.

        Повторяет запрос один раз, если первый ответ не разбирается.
        """
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
            )
            try:
                data = _extract_json(raw)
                return schema.model_validate(data)
            except (ValueError, ValidationError) as exc:
                last_error = exc
                logger.info("Не удалось разобрать JSON (попытка %s): %s", attempt + 1, exc)
        raise LlmResponseError(str(last_error)) from last_error

    async def ping_brain(self) -> bool:
        """Проверяет, отвечает ли текстовый сервер."""
        return await self._ping(self._brain)

    async def ping_eyes(self) -> bool:
        """Проверяет, отвечает ли vision-сервер."""
        return await self._ping(self._eyes)

    async def _ping(self, client: AsyncOpenAI) -> bool:
        try:
            await client.models.list()
            return True
        except Exception:
            logger.debug("Пинг llama-server не удался", exc_info=True)
            return False


def _extract_json(text: str) -> Any:
    """Достаёт JSON из сырого ответа модели."""
    text = text.strip()
    fence = _JSON_FENCE.search(text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise ValueError("в ответе нет JSON-объекта")


_client: LlmClient | None = None


def get_llm() -> LlmClient:
    """Возвращает общий клиент LLM."""
    global _client
    if _client is None:
        _client = LlmClient()
    return _client

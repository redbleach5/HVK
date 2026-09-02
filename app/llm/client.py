"""Клиент к двум llama-server: мозг (текст) и глаза (фото)."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, TypeVar

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, OpenAIError
from pydantic import BaseModel, ValidationError
import httpx

from app.config import get_settings
from app.diagnostics.metrics import LlmCallMetric, record_call
from app.idle.state import llm_enter, llm_leave
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


def _fallback_json_text(message: object) -> str:
    """Ollama/qwen иногда отдаёт JSON в reasoning, а content пуст."""
    parts: list[str] = []
    content = _as_text(getattr(message, "content", None)).strip()
    if content:
        parts.append(content)
    thinking = _message_thinking(message)
    if thinking:
        parts.append(thinking)
    for src in parts:
        if "{" in src:
            return src
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


def _normalize_tool_calls(raw: object) -> list[dict[str, Any]]:
    """Ollama stream: tool_calls целиком или кусками."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        fn = item.get("function") if isinstance(item.get("function"), dict) else item
        name = str(fn.get("name") or "").strip()
        if not name:
            continue
        args: Any = fn.get("arguments")
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {"query": args}
        if not isinstance(args, dict):
            args = {}
        out.append(
            {
                "type": "function",
                "function": {
                    "index": fn.get("index", len(out)),
                    "name": name,
                    "arguments": args,
                },
            }
        )
    return out


def _tool_label(calls: list[dict[str, Any]]) -> str:
    bits: list[str] = []
    for call in calls:
        fn = call.get("function") or {}
        args = fn.get("arguments") or {}
        name = str(fn.get("name") or "")
        q = str(args.get("query") or args.get("url") or args.get("q") or "").strip()
        bits.append(f"{name}: {q}" if q else name)
    return "; ".join(bits)[:240]


def _schema_hint(schema: type[BaseModel]) -> str:
    """Короткая подсказка полей — не тащить полную JSON Schema в промпт."""

    def _shape(model: type[BaseModel]) -> str:
        parts: list[str] = []
        for name, field in model.model_fields.items():
            ann = field.annotation
            origin = getattr(ann, "__origin__", None)
            if origin is list:
                args = getattr(ann, "__args__", ())
                inner = args[0] if args else None
                if isinstance(inner, type) and issubclass(inner, BaseModel):
                    parts.append(f'{name}: [{{{", ".join(inner.model_fields.keys())}}}]')
                else:
                    parts.append(f"{name}: [...]")
            elif isinstance(ann, type) and issubclass(ann, BaseModel):
                parts.append(f'{name}: {{{", ".join(ann.model_fields.keys())}}}')
            else:
                parts.append(name)
        return ", ".join(parts)

    return f"JSON-объект: {_shape(schema)}."


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
        self._keep_alive = settings.llm_keep_alive
        self._num_ctx = max(4096, int(settings.brain_num_ctx or 16384))
        self._think_tokens = max(512, int(settings.brain_think_tokens or 2500))
        self._reply_tokens = max(512, int(settings.brain_reply_tokens or 2000))

    @property
    def thoughtful_max_tokens(self) -> int:
        """Мысль + реплика одного хода. Не делят остаток после архива."""
        from app.context.budget import generation_budget

        return generation_budget(
            think_tokens=self._think_tokens, reply_tokens=self._reply_tokens
        )

    def fit_chat_user(
        self,
        system: str,
        user: str,
        *,
        num_ctx: int | None = None,
        gen_tokens: int | None = None,
    ) -> str:
        """Сжимает старое в промпте, чтобы хватило на ход мысли."""
        from app.context.budget import (
            estimate_tokens,
            fit_user_prompt,
            generation_budget,
            prompt_budget,
        )

        ctx = max(4096, int(num_ctx or self._num_ctx))
        if gen_tokens is not None:
            gen = max(512, int(gen_tokens))
        else:
            gen = generation_budget(
                think_tokens=self._think_tokens, reply_tokens=self._reply_tokens
            )
        room = prompt_budget(ctx, gen) - estimate_tokens(system or "")
        return fit_user_prompt(user, max_tokens=room)

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
        label: str = "",
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

        t0 = time.perf_counter()
        await llm_enter()
        try:
            text = ""
            message = None
            for json_try in range(2 if json_object else 1):
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
                        "keep_alive": self._keep_alive,
                        "options": {
                            "num_ctx": self._num_ctx if json_object else self._num_ctx,
                            "num_predict": max_tokens,
                        },
                        **({"format": "json"} if json_object else {}),
                    },
                )
                message = response.choices[0].message
                text = (message.content or "").strip()
                if no_reasoning and not json_object:
                    text = strip_cot(text)
                if not text and json_object:
                    text = _fallback_json_text(message)
                    if text:
                        logger.info("JSON: content пуст — взяли из reasoning")
                if text or not json_object:
                    break
                logger.info("JSON: пустой ответ — повтор %s", json_try + 2)
            if not text:
                if not json_object:
                    await record_call(
                        LlmCallMetric(
                            kind="complete",
                            label=label or ("vision" if images else "text"),
                            duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                            ok=False,
                            error="empty",
                        )
                    )
                raise LlmResponseError("пустой ответ модели")
            if not json_object:
                await record_call(
                    LlmCallMetric(
                        kind="complete",
                        label=label or ("vision" if images else "text"),
                        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                        ok=True,
                        extra={"chars": len(text), "max_tokens": max_tokens},
                    )
                )
            return text
        except (APIConnectionError, APITimeoutError) as exc:
            logger.warning("Модель недоступна: %s", exc)
            if not json_object:
                await record_call(
                    LlmCallMetric(
                        kind="complete",
                        label=label or ("vision" if images else "text"),
                        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                        ok=False,
                        error=str(exc)[:200],
                    )
                )
            raise ModelAsleepError(str(exc)) from exc
        except OpenAIError as exc:
            logger.exception("Ошибка llama-server")
            if not json_object:
                await record_call(
                    LlmCallMetric(
                        kind="complete",
                        label=label or ("vision" if images else "text"),
                        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                        ok=False,
                        error=str(exc)[:200],
                    )
                )
            raise ModelAsleepError(str(exc)) from exc
        finally:
            await llm_leave()

    async def _complete_ollama_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """JSON через нативный Ollama /api/chat — надёжнее OpenAI-compat на длинных промптах."""
        payload = {
            "model": self._brain_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "think": False,
            "format": "json",
            "keep_alive": self._keep_alive,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self._num_ctx,
            },
        }
        timeout = httpx.Timeout(self._llm_timeout, connect=20.0)
        await llm_enter()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self._brain_chat_url, json=payload)
                response.raise_for_status()
                data = response.json()
            message = data.get("message") or {}
            text = _as_text(message.get("content")).strip()
            if not text:
                text = _as_text(message.get("thinking")).strip()
            if not text:
                raise LlmResponseError("пустой ответ модели")
            return text
        except httpx.HTTPError as exc:
            logger.warning("Модель недоступна: %s", exc)
            raise ModelAsleepError(str(exc)) from exc
        finally:
            await llm_leave()

    def _chat_payload(
        self,
        *,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        stream: bool,
        think: bool,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._brain_model,
            "messages": messages,
            "stream": stream,
            "think": think,
            "keep_alive": self._keep_alive,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self._num_ctx,
            },
        }
        if tools:
            payload["tools"] = tools
        return payload

    def _thought_payload(
        self,
        *,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> dict[str, Any]:
        return self._chat_payload(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            think=True,
        )

    async def complete_thoughtful(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.4,
        max_tokens: int | None = None,
    ) -> tuple[str, str]:
        """Ответ + отдельный ход мысли. Мысль не смешивается с репликой."""
        max_tokens = max_tokens or self.thoughtful_max_tokens
        timeout = httpx.Timeout(self._llm_timeout, connect=20.0)
        await llm_enter()
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
            message = data.get("message") or {}
            text = strip_cot(_as_text(message.get("content")).strip())
            thinking = _as_text(message.get("thinking")).strip()
            if not text:
                raise LlmResponseError("пустой ответ модели")
            return text, thinking
        except httpx.HTTPError as exc:
            logger.warning("Модель недоступна: %s", exc)
            raise ModelAsleepError(str(exc)) from exc
        finally:
            await llm_leave()

    async def stream_thoughtful(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.4,
        max_tokens: int | None = None,
        label: str = "chat",
        tools: list[dict[str, Any]] | None = None,
        execute_tool: Any | None = None,
        max_tool_rounds: int = 3,
    ):
        """Стримит ход мысли, реплику и, если нужно, вызовы инструментов."""
        max_tokens = max_tokens or self.thoughtful_max_tokens
        t0 = time.perf_counter()
        ok = False
        err = ""
        await llm_enter()
        try:
            if tools and execute_tool:
                async for item in self._stream_with_tools(
                    system=system,
                    user=user,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    execute_tool=execute_tool,
                    max_tool_rounds=max_tool_rounds,
                ):
                    ok = True
                    yield item
            else:
                async for item in self._stream_thoughtful_inner(
                    system=system,
                    user=user,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    ok = True
                    yield item
        except Exception as exc:
            err = str(exc)[:200]
            raise
        finally:
            await llm_leave()
            await record_call(
                LlmCallMetric(
                    kind="stream",
                    label=label,
                    duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                    ok=ok and not err,
                    error=err,
                )
            )

    async def _stream_with_tools(
        self,
        *,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        tools: list[dict[str, Any]],
        execute_tool: Any,
        max_tool_rounds: int,
    ):
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        for step in range(max_tool_rounds + 1):
            round_data: dict[str, Any] = {}
            async for kind, payload in self._stream_round(
                messages,
                temperature=temperature,
                max_tokens=max_tokens,
                think=True,
                tools=tools,
            ):
                if kind in ("thinking", "text"):
                    yield (kind, payload)
                else:
                    round_data = payload
            calls = round_data.get("tool_calls") or []
            content = round_data.get("content") or ""
            thinking = round_data.get("thinking") or ""
            if not calls and not content and thinking and step == 0:
                async for kind, payload in self._stream_round(
                    messages,
                    temperature=temperature,
                    max_tokens=min(800, max_tokens),
                    think=False,
                    tools=tools,
                ):
                    if kind in ("thinking", "text"):
                        yield (kind, payload)
                    else:
                        round_data = payload
                calls = round_data.get("tool_calls") or []
                content = round_data.get("content") or ""
                thinking = round_data.get("thinking") or thinking
            if not calls:
                break
            yield ("search", _tool_label(calls))
            messages.append(
                {
                    "role": "assistant",
                    "content": content,
                    "thinking": thinking,
                    "tool_calls": calls,
                }
            )
            for call in calls:
                fn = call.get("function") or {}
                name = str(fn.get("name") or "")
                args = fn.get("arguments") or {}
                result = await execute_tool(name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": name,
                        "content": str(result)[:8000],
                    }
                )

    async def _stream_thoughtful_inner(
        self,
        *,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
    ):
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        async for kind, payload in self._stream_round(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            think=True,
            tools=None,
        ):
            if kind in ("thinking", "text"):
                yield (kind, payload)

    async def _stream_round(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float,
        max_tokens: int,
        think: bool,
        tools: list[dict[str, Any]] | None,
    ):
        timeout = httpx.Timeout(connect=20.0, read=None, write=120.0, pool=20.0)
        payload = self._chat_payload(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            think=think,
            tools=tools,
        )
        seen_thought = ""
        seen_text = ""
        calls: list[dict[str, Any]] = []
        n_chunks = 0
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
                        n_chunks += 1
                        message = chunk.get("message") or {}
                        thought = _as_text(message.get("thinking"))
                        if thought:
                            if thought.startswith(seen_thought):
                                delta = thought[len(seen_thought) :]
                                seen_thought = thought
                            else:
                                delta = thought
                                seen_thought += thought
                            if delta:
                                yield ("thinking", delta)
                        piece = _as_text(message.get("content"))
                        if piece:
                            if piece.startswith(seen_text):
                                delta = piece[len(seen_text) :]
                                seen_text = piece
                            else:
                                delta = piece
                                seen_text += piece
                            if delta:
                                yield ("text", delta)
                        parsed = _normalize_tool_calls(message.get("tool_calls"))
                        if parsed:
                            calls = parsed
            logger.info(
                "llm stream chunks=%s think_chars=%s text_chars=%s tools=%s think=%s",
                n_chunks,
                len(seen_thought),
                len(seen_text),
                [c.get("function", {}).get("name") for c in calls],
                think,
            )
            yield (
                "round",
                {
                    "thinking": seen_thought,
                    "content": seen_text,
                    "tool_calls": calls,
                },
            )
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
        label: str = "",
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
                "Не используй markdown-ограждения. "
                f"{_schema_hint(schema)}"
            )
        json_ctx = self._num_ctx
        fitted_user = self.fit_chat_user(
            json_system,
            user,
            num_ctx=json_ctx,
            gen_tokens=max_tokens,
        )
        last_error: Exception | None = None
        t0 = time.perf_counter()
        for attempt in range(2):
            try:
                prompt_user = fitted_user if attempt == 0 else (
                    fitted_user + "\n\nПредыдущий ответ был невалидным JSON. Верни только корректный JSON."
                )
                if images:
                    raw = await self.complete(
                        system=json_system,
                        user=prompt_user,
                        images=images,
                        # Ретрай поднимает температуру: первый сбой уже
                        # случился, детерминированный повтор его повторит.
                        temperature=temperature if attempt == 0 else min(temperature + 0.15, 0.85),
                        max_tokens=max_tokens,
                        no_reasoning=True,
                        json_object=False,
                        label=label or "json",
                    )
                else:
                    raw = await self._complete_ollama_json(
                        system=json_system,
                        user=prompt_user,
                        # Ретрай поднимает температуру: первый сбой уже
                        # случился, детерминированный повтор его повторит.
                        temperature=temperature if attempt == 0 else min(temperature + 0.15, 0.85),
                        max_tokens=max_tokens,
                    )
                data = _extract_json(raw)
                result = schema.model_validate(data)
                await record_call(
                    LlmCallMetric(
                        kind="complete_json",
                        label=label or "json",
                        duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                        ok=True,
                        extra={"attempt": attempt + 1, "max_tokens": max_tokens},
                    )
                )
                return result
            except (ValueError, ValidationError) as exc:
                last_error = exc
                logger.info(
                    "Не удалось разобрать JSON (попытка %s): %s",
                    attempt + 1,
                    exc,
                )
        await record_call(
            LlmCallMetric(
                kind="complete_json",
                label=label or "json",
                duration_ms=round((time.perf_counter() - t0) * 1000, 1),
                ok=False,
                error=str(last_error)[:200],
            )
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
            return response.status_code == 200
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
        if any(
            k in obj
            for k in (
                "verdict", "why", "caption_direction", "advice",
                "ideas", "portrait", "status", "tone", "body",
            )
        ):
            return obj
    return found[0]


_client: LlmClient | None = None


def get_llm() -> LlmClient:
    """Возвращает общий клиент LLM."""
    global _client
    if _client is None:
        _client = LlmClient()
    return _client

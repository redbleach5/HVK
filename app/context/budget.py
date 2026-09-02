"""Бюджет окна: мысль и ответ не должны быть вытеснены архивом.

Как у Claude/Cursor: текущий ход мысли — в резерве, сжимаем старое, не файл.
"""

from __future__ import annotations

import re

_SESSION_BLOCK = re.compile(
    r"\n\nУЖЕ ОТКРЫТО В ЭТОМ ДИАЛОГЕ:\n.*?(?=\n\nДОПОЛНИТЕЛЬНО:|\n\nНедавний диалог:|\Z)",
    re.S,
)
_EXTRA_BLOCK = re.compile(r"\n\nДОПОЛНИТЕЛЬНО:\n.*?(?=\n\nНедавний диалог:|\Z)", re.S)


def estimate_tokens(text: str) -> int:
    """Грубая, намеренно консервативная оценка: кириллица ~2 символа на токен.

    Замеры scripts/_probe_context_spend.py talk: реальный prompt_eval_count у
    qwen3:27b ≈ 0.65× этой оценки (~3.1 символа на токен). Коэффициент оставляем
    консервативным намеренно: резерв на мысль+ответ не должен быть съеден.
    """
    return max(1, (len(text or "") + 1) // 2)


def generation_budget(*, think_tokens: int, reply_tokens: int) -> int:
    """Сколько токенов оставить на мысль + реплику в этом ходе."""
    think = max(512, int(think_tokens or 0))
    reply = max(512, int(reply_tokens or 0))
    return think + reply


def prompt_budget(num_ctx: int, generation: int) -> int:
    """Сколько токенов можно отдать промпту, чтобы мысль не обрезалась."""
    ctx = max(4096, int(num_ctx or 16384))
    gen = max(1024, int(generation or 0))
    return max(2048, ctx - gen - 256)


def fit_user_prompt(user: str, *, max_tokens: int) -> str:
    """Сжимает промпт: сначала набор диалога, потом «дополнительно». Вопрос не трогает."""
    text = user or ""
    limit = max(800, int(max_tokens or 0))
    if estimate_tokens(text) <= limit:
        return text
    trimmed = _SESSION_BLOCK.sub("\n", text, count=1)
    if estimate_tokens(trimmed) <= limit:
        return trimmed.strip()
    trimmed = _EXTRA_BLOCK.sub("\n", trimmed, count=1)
    if estimate_tokens(trimmed) <= limit:
        return trimmed.strip()
    # Режем хвост до маркера текущего сообщения — его оставляем.
    marker = "Сообщение автора:"
    idx = trimmed.rfind(marker)
    if idx == -1:
        cap = limit * 2
        return trimmed[:cap].rstrip() + "…"
    head = trimmed[:idx].rstrip()
    tail = trimmed[idx:]
    prefix = marker + "\n"
    if tail.startswith(prefix):
        body = tail[len(prefix) :]
        max_body_chars = max(8000, limit * 2)
        if len(body) > max_body_chars:
            body = (
                body[:max_body_chars].rstrip()
                + "\n… (сообщение сокращено для окна модели)"
            )
            tail = prefix + body
    cap = max(400, limit * 2 - len(tail))
    if len(head) > cap:
        head = head[:cap].rstrip() + "\n…"
    return f"{head}\n\n{tail}".strip()

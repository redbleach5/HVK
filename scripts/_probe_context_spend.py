# -*- coding: utf-8 -*-
"""Разговор с моделью без обвинений: сначала смотрим, ЧТО мы ей шлём.

Режимы:
  static — собрать реальные промпты (чат, идеи, редактор), показать размеры
           секций и дубли (пост в нескольких секциях, голос дважды).
  talk   — два хода живого чата через продакшн-путь (think:true, num_ctx),
           замер реальных токенов Ollama (prompt_eval_count/eval_count),
           проверка цитат: каждый «пост #N» должен быть в контексте.

Модель не обвиняем: если ответ кривой — ищем, что мы ей подсунули.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.context.budget import estimate_tokens  # noqa: E402
from app.context.engine import ContextEngine  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.memory.store import MemoryStore  # noqa: E402
from app.memory.working import clear_working  # noqa: E402
from app.agents.base import pack_for_agent  # noqa: E402
from app.agents.chat import _chat_system, _general_chat_user  # noqa: E402

SECTION_MARKERS = (
    "КОНТЕКСТ СЕЙЧАС",
    "Недавние посты (кратко):",
    "Что лучше всего заходило за последние недели:",
    "Незакрытые идеи в плане:",
    "Не повторять темы:",
    "ПАМЯТЬ АВТОРА",
    "Голос:",
    "ПО ЭТОМУ ВОПРОСУ",
    "УЖЕ ОТКРЫТО В ЭТОМ ДИАЛОГЕ:",
    "ДОПОЛНИТЕЛЬНО:",
    "Недавний диалог:",
    "Сообщение автора:",
)


def sections(text: str) -> list[tuple[str, str]]:
    """Разрезает промпт по известным заголовкам, сохраняя порядок."""
    marks: list[tuple[int, str]] = []
    for marker in SECTION_MARKERS:
        idx = text.find(marker)
        if idx >= 0:
            marks.append((idx, marker))
    marks.sort()
    out: list[tuple[str, str]] = []
    for i, (idx, marker) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out.append((marker, text[idx:end]))
    return out


def show_sections(title: str, text: str) -> None:
    print(f"\n--- {title}: {len(text)} симв. ~{estimate_tokens(text)} ток (оценка) ---")
    for marker, body in sections(text):
        print(
            f"  {marker:<44} {len(body):>6} симв. ~{estimate_tokens(body):>5} ток"
        )


def ids_in(text: str) -> set[int]:
    return {int(x) for x in re.findall(r"пост #(\d+)", text)}


def dup_report(name: str, context: str, pack_posts: list) -> None:
    hits_sec = next((b for m, b in sections(context) if m.startswith("Что лучше")), "")
    full_sec = next((b for m, b in sections(context) if m.startswith("ПО ЭТОМУ")), "")
    recent_sec = next(
        (b for m, b in sections(context) if m.startswith("Недавние посты")), ""
    )
    dup_hf = ids_in(hits_sec) & ids_in(full_sec)
    recent_in_full = 0
    for post in pack_posts:
        snippet = " ".join((post.text or "").split())[:60]
        if snippet and snippet in recent_sec and post.id in ids_in(full_sec):
            recent_in_full += 1
    print(
        f"[{name}] дубли: хиты∩полные={sorted(dup_hf) or '—'}; "
        f"недавние∩полные={recent_in_full}"
    )


async def static_mode() -> int:
    clear_working()
    async with SessionLocal() as session:
        memory = MemoryStore(session)
        # --- Чат: живое сообщение автора ---
        msg1 = "сил мало, а хочется что-то тёплое выложить. что посоветуешь?"
        context1, _labels1 = await pack_for_agent(session, query=msg1)
        user1 = _general_chat_user(context1, "", msg1)
        show_sections(f"чат, ход 1 (system {_len(_chat_system())} симв. отдельно)", user1)
        dup_report("чат-1", context1, [])

        # --- Идеи: как их собирает ideas.py ---
        recent_themes = await memory.recent_idea_themes(20)
        anti = await memory.antipathy_topics()
        snippets = []
        for post in await memory.recent_posts(6):
            theme = post.theme or "без темы"
            body = (post.text or "").strip().replace("\n", " ")[:220]
            snippets.append(f"— {theme}: {body}")
        archive_block = "\n".join(snippets) or "(пусто)"
        extra_ideas = (
            f"Недавние темы идей (не повторять): {', '.join(recent_themes) or 'нет'}\n"
            f"Антипатии: {', '.join(anti) or 'нет'}\n"
            f"Архив автора (опирайся только на это, цитируй в why.related_posts):\n{archive_block}"
        )
        context_i, _li = await pack_for_agent(
            session, extra=extra_ideas, with_session=False
        )
        recent6_ids = [p.id for p in await memory.recent_posts(6)]
        dup_ideas = [pid for pid in recent6_ids if f"пост #{pid}" in context_i]
        show_sections("идеи", context_i)
        print(f"[идеи] недавние 6 постов уже видны в контексте: {dup_ideas or '—'}")

        # --- Редактор: голос дважды? ---
        draft = (
            "Купила сегодня новую кружку, мягкий свет из окна. "
            "Хочется короткий текст про тихое утро."
        )
        context_e, _le = await pack_for_agent(
            session, query=draft, with_session=False, include_voice=False
        )
        voice = await memory.latest_voice()
        profile_size = len(json.dumps(voice.profile, ensure_ascii=False)) if voice else 0
        voice_in_memory = next(
            (b for m, b in sections(context_e) if m == "Голос:"), ""
        )
        print(
            f"\n[редактор] полный профиль голоса {profile_size} симв. "
            f"+ сводка в памяти {len(voice_in_memory)} симв. (дубль)"
        )
        show_sections("редактор (user, без system)", context_e)
    return 0


def _len(text: str) -> int:
    return len(text or "")


def _chat_url() -> str:
    base = get_settings().brain_base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base + "/api/chat"


async def talk_turn(
    *, system: str, user: str, history: list[dict[str, str]]
) -> tuple[str, dict]:
    """Ход через продакшн-путь: think:true, num_ctx из настроек."""
    settings = get_settings()
    messages = [
        {"role": "system", "content": system},
        *history,
        {"role": "user", "content": user},
    ]
    payload = {
        "model": settings.brain_model,
        "messages": messages,
        "stream": False,
        "think": True,
        "options": {
            "temperature": 0.4,
            "num_predict": settings.brain_think_tokens + settings.brain_reply_tokens,
            "num_ctx": settings.brain_num_ctx,
        },
    }
    t0 = time.perf_counter()
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.llm_timeout, connect=20.0)
    ) as client:
        response = await client.post(_chat_url(), json=payload)
        response.raise_for_status()
        data = response.json()
    seconds = round(time.perf_counter() - t0, 1)
    message = data.get("message") or {}
    usage = {
        "seconds": seconds,
        "prompt_tokens": int(data.get("prompt_eval_count") or 0),
        "reply_tokens": int(data.get("eval_count") or 0),
        "thinking_chars": len(message.get("thinking") or ""),
        "reply_chars": len(message.get("content") or ""),
    }
    return (message.get("content") or "").strip(), usage


def cite_check(reply: str, allowed: set[int]) -> list[int]:
    cited = {int(x) for x in re.findall(r"пост #(\d+)", reply)}
    return sorted(cited - allowed)


async def talk_mode() -> int:
    clear_working()
    async with SessionLocal() as session:
        system = _chat_system()

        msg1 = "сил мало, а хочется что-то тёплое выложить. что посоветуешь?"
        pack1 = await ContextEngine(session).pack(query=msg1)
        allowed1 = {p.id for p in pack1.posts if p.id}
        user1 = _general_chat_user(pack1.text, "", msg1)
        est1 = estimate_tokens(system) + estimate_tokens(user1)
        reply1, usage1 = await talk_turn(system=system, user=user1, history=[])
        print(
            f"\n--- ход 1: оценка {est1} ток, факт {usage1['prompt_tokens']} ток "
            f"(x{usage1['prompt_tokens'] / max(est1, 1):.2f}); ответ {usage1['reply_tokens']} ток, "
            f"мысль {usage1['thinking_chars']} симв., {usage1['seconds']} c ---"
        )
        print("ответ 1:", reply1[:400].replace("\n", " "))
        bad1 = cite_check(reply1, allowed1)
        print("цитаты вне контекста:", bad1 or "—")

        msg2 = "а можно про дочку и чай? только коротко"
        hist = f"автор: {msg1}\nредакция: {reply1[:1800]}"
        pack2 = await ContextEngine(session).pack(query=msg2)
        allowed2 = {p.id for p in pack2.posts if p.id}
        user2 = _general_chat_user(pack2.text, hist, msg2)
        est2 = estimate_tokens(system) + estimate_tokens(user2)
        reply2, usage2 = await talk_turn(system=system, user=user2, history=[])
        print(
            f"\n--- ход 2: оценка {est2} ток, факт {usage2['prompt_tokens']} ток "
            f"(x{usage2['prompt_tokens'] / max(est2, 1):.2f}); ответ {usage2['reply_tokens']} ток, "
            f"мысль {usage2['thinking_chars']} симв., {usage2['seconds']} c ---"
        )
        print("ответ 2:", reply2[:400].replace("\n", " "))
        bad2 = cite_check(reply2, allowed2)

    print("цитаты вне контекста:", bad2 or "—")
    problems = bad1 + bad2
    if not reply1 or not reply2:
        print("\nПРОВАЛ: модель ответила пустотой — смотрим наш промпт, не её")
        return 1
    if problems:
        print(f"\nПРОВАЛ: модель процитировала посты, которых мы не давали: {problems}")
        return 1
    print("\nОК: цитаты в рамках контекста; замеры выше — материал для оптимизации расхода")
    return 0


async def main() -> int:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "static").lower()
    if mode == "static":
        return await static_mode()
    if mode == "talk":
        return await talk_mode()
    print("режимы: static | talk")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))


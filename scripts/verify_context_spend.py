# -*- coding: utf-8 -*-
"""Регрессионный страж расхода контекста (без LLM).

Закрепляет правки контекста, чтобы они не выползали обратно:
1. Chat: хит не показан дважды (в «Что лучше всего заходило» и целиком в
   «ПО ЭТОМУ ВОПРОСУ»); в памяти есть строка «Голос:»; оценка промпта в бюджете.
2. Ideas: никакого «УЖЕ ОТКРЫТО В ЭТОМ ДИАЛОГЕ» — чужой диалог не утекает.
3. Editor: голос не продублирован (include_voice=False → нет строки «Голос:»).
Если что-то сломалось — возвращает 1 и говорит, что именно.
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.agents.base import pack_for_agent  # noqa: E402
from app.agents.chat import _chat_system, _general_chat_user  # noqa: E402
from app.context.budget import estimate_tokens  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.memory.store import MemoryStore  # noqa: E402
from app.memory.working import clear_working  # noqa: E402

MSG = "сил мало, а хочется что-то тёплое выложить. что посоветуешь?"
DRAFT = "Купила сегодня новую кружку, мягкий свет из окна. Хочется короткий текст про тихое утро."
CHAT_CAP = 9000  # оценка (system+user) выше — контекст расползается

_PROBLEMS: list[str] = []


def _post_ids(text: str) -> set[int]:
    return {int(x) for x in re.findall(r"пост #(\d+)", text)}


def _section(text: str, marker: str) -> str:
    """Текст секции от marker до следующего известного заголовка."""
    idx = text.find(marker)
    if idx < 0:
        return ""
    start = idx + len(marker)
    stops = (
        "Незакрытые идеи в плане:",
        "УЖЕ ОТКРЫТО В ЭТОМ ДИАЛОГЕ:",
        "ДОПОЛНИТЕЛЬНО:",
        "Недавний диалог:",
        "Сообщение автора:",
    )
    ends = [text.find(s, start) for s in stops if text.find(s, start) >= 0]
    end = min(ends) if ends else len(text)
    return text[start:end]


async def main() -> int:
    clear_working()
    async with SessionLocal() as session:
        # 1) Чат
        ctx, _ = await pack_for_agent(session, query=MSG)
        user = _general_chat_user(ctx, "", MSG)
        system = _chat_system()
        est = estimate_tokens(system) + estimate_tokens(user)
        hits = _section(ctx, "Что лучше всего заходило за последние недели:")
        full = _section(ctx, "ПО ЭТОМУ ВОПРОСУ")
        dup = _post_ids(hits) & _post_ids(full)
        print(f"[chat] оценка ~{est} ток; дублей «хит ∩ полные»: {sorted(dup) or '—'}")
        if dup:
            _PROBLEMS.append(f"chat: дубли хитов {sorted(dup)}")
        voice = await MemoryStore(session).latest_voice()
        if voice is not None and "Голос:" not in ctx:
            _PROBLEMS.append("chat: в памяти нет строки «Голос:»")
        if est > CHAT_CAP:
            _PROBLEMS.append(f"chat: оценка {est} превысила {CHAT_CAP}")

        # 2) Идеи — чужой диалог не утекает
        ctx_i, _ = await pack_for_agent(
            session, extra="архив-блок идей", with_session=False
        )
        if "УЖЕ ОТКРЫТО В ЭТОМ ДИАЛОГЕ:" in ctx_i:
            _PROBLEMS.append("ideas: чужой рабочий набор чата утёк в промпт идей")
        else:
            print("[ideas] рабочего набора чата в промпте нет")

        # 3) Редактор — голос не продублирован
        ctx_e, _ = await pack_for_agent(
            session, query=DRAFT, with_session=False, include_voice=False
        )
        if "Голос:" in ctx_e:
            _PROBLEMS.append(
                "editor: голос продублирован (include_voice=False не сработал)"
            )
        else:
            print("[editor] голос в контексте не продублирован")

    if _PROBLEMS:
        print("\nПРОВАЛ:")
        for p in _PROBLEMS:
            print(f"  - {p}")
        return 1
    print("\nОК: контекст в норме (нет дублей, нет утечек, бюджет держится)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
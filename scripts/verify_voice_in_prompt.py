# -*- coding: utf-8 -*-
"""Голос в общем промпте: интонации и запреты доходят до всех агентов.

Без LLM. Проверяет MemoryStore.prompt_block():
1) если в профиле есть sample_phrases — блок показывает интонации;
2) если есть forbidden_vibes — блок показывает «чего в голосе нет»;
3) блок памяти не разросся.
Если профиля голоса ещё нет — честно сообщает и не считает это провалом.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.memory.store import MemoryStore  # noqa: E402

MAX_BLOCK = 6000


async def main() -> int:
    async with SessionLocal() as session:
        memory = MemoryStore(session)
        voice = await memory.latest_voice()
        block = await memory.prompt_block()
    if voice is None:
        print("профиля голоса ещё нет — проверять нечего (не провал)")
        return 0
    profile = voice.profile or {}
    phrases = [
        str(s).strip()
        for s in (profile.get("sample_phrases") or [])
        if str(s).strip()
    ]
    forbidden = [
        str(s).strip()
        for s in (profile.get("forbidden_vibes") or [])
        if str(s).strip()
    ]

    ok = True
    if phrases:
        needle = phrases[0][:30]
        if "Как звучит её интонация" not in block or needle not in block:
            print(f"ПРОВАЛ: интонации не дошли до промпта (ищу: {needle!r})")
            ok = False
        else:
            print(f"интонации в промпте: {min(3, len(phrases))} из {len(phrases)}")
    else:
        print("в профиле нет sample_phrases — поле необязательное")
    if forbidden:
        needle = forbidden[0][:30]
        if "Чего в её голосе нет" not in block or needle not in block:
            print(f"ПРОВАЛ: запреты голоса не дошли до промпта (ищу: {needle!r})")
            ok = False
        else:
            print(f"запреты голоса в промпте: {min(4, len(forbidden))} из {len(forbidden)}")
    else:
        print("в профиле нет forbidden_vibes — поле необязательное")

    if len(block) > MAX_BLOCK:
        print(f"ПРОВАЛ: блок памяти разросся: {len(block)} символов")
        ok = False
    else:
        print(f"блок памяти компактный: {len(block)} символов")
    if not ok:
        return 1
    print("ОК: голос теперь в общем промпте всех агентов")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

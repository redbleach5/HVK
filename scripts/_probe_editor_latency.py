# -*- coding: utf-8 -*-
"""Латентность JSON-пути продакшн-клиента: холодный и тёплый вызов.

Проверяет keep_alive (мозг не выгружается между вызовами) и то, что
complete_json с think:false отвечает быстро и валидным JSON.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from pydantic import BaseModel  # noqa: E402

from app.llm.client import get_llm  # noqa: E402


class _Out(BaseModel):
    revised_text: str
    why_summary: str = ""


DRAFT = (
    "Черновик: Я думала, что осень — это время для тёплых пледов и чашки чая. "
    "Но сегодня проснулась и поняла, что мне нужно больше света.\n"
    "Сделай лёгкую редактуру черновика. Верни revised_text и why_summary (одно предложение)."
)


async def one(llm, n: int) -> float:
    t0 = time.perf_counter()
    out = await llm.complete_json(
        system=(
            "Ты редактор текста. Сохраняй голос автора. "
            "Не меняй смысл, не добавляй фактов."
        ),
        user=DRAFT,
        schema=_Out,
        temperature=0.5,
        max_tokens=2400,
        label="editor_probe",
    )
    dt = time.perf_counter() - t0
    text = (out.revised_text or "").strip()
    print(f"вызов {n}: {dt:.0f}с, revised_text {len(text)} симв.", flush=True)
    print("  ", text[:160].replace("\n", " "), flush=True)
    return dt


async def main() -> int:
    llm = get_llm()
    t1 = await one(llm, 1)
    t2 = await one(llm, 2)
    print(f"сравнение: первый {t1:.0f}с, второй {t2:.0f}с", flush=True)
    if t2 > t1 + 15:
        print("ПРОВАЛ: тёплый вызов заметно дольше — keep_alive не работает?")
        return 1
    print("ОК: JSON-путь отвечает валидным JSON, мозг остаётся резидентным")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

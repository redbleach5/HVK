# -*- coding: utf-8 -*-
"""Bake-off локальных моделей на задачах Тихой редакции.

Для каждой модели два прогона:
1) эмпатичный ответ с цитатой из архива (стиль, опора на пост);
2) строгий JSON (think:false), проверка парсинга.
Метрики: суммарное время, токены ответа, ток/сек.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API = "http://127.0.0.1:11434/api/chat"
MODELS = ["qwen3.8:27b", "qwen3.6:latest", "gpt-oss:20b"]

QUOTE = (
    "Утром заварила чай в любимой чашке — пар, тишина, свет на столе. "
    "Никуда не спешу."
)
STYLE_SYSTEM = (
    "Ты помощник личного блога «Красивое в обычном». Не пиши посты за автора. "
    "Отвечай коротко (3-5 предложений), тепло, её языком. Опирайся на её посты, "
    "цитируй их и объясняй, почему предложение подходит."
)
STYLE_USER = (
    f"Её пост по теме:\n«{QUOTE}»\n\n"
    "Сообщение автора: сил мало, а хочется что-то тёплое выложить. "
    "что посоветуешь?"
)
JSON_SYSTEM = (
    "Ты агент идей личного блога. Отвечай ТОЛЬКО валидным JSON без markdown."
)
JSON_USER = (
    f"Её пост:\n«{QUOTE}»\n\n"
    'Верни JSON: {"ideas": [{"title": str, "why": str, "cite_post_id": int}]} '
    "— две идеи выкладки на сегодня, почему подходят, ссылка на её пост."
)


def chat(model: str, system: str, user: str, *, think: bool) -> tuple[str, float, dict]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"num_ctx": 8192},
    }
    payload["think"] = think
    req = urllib.request.Request(
        API,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    dt = time.perf_counter() - t0
    content = (data.get("message") or {}).get("content") or ""
    metrics = {
        "load_s": round(data.get("load_duration", 0) / 1e9, 1),
        "eval_s": round(data.get("eval_duration", 0) / 1e9, 1),
        "eval_tokens": data.get("eval_count", 0),
        "prompt_tokens": data.get("prompt_eval_count", 0),
    }
    return content, dt, metrics


def main() -> int:
    report: list[dict] = []
    for model in MODELS:
        print(f"\n===== {model} =====", flush=True)
        # 1) стиль
        try:
            text, dt, m = chat(model, STYLE_SYSTEM, STYLE_USER, think=True)
            tps = m["eval_tokens"] / m["eval_s"] if m["eval_s"] else 0
            print(
                f"[стиль] {dt:.1f}s (load {m['load_s']}s), "
                f"{m['eval_tokens']} ток. @ {tps:.1f} т/с, промпт {m['prompt_tokens']}"
            )
            print(text.strip()[:900])
        except Exception as e:
            print(f"[стиль] ОШИБКА: {e}")
            text, dt, m, tps = "", 0, {}, 0
        # 2) JSON
        ok_json = False
        try:
            jtext, jdt, jm = chat(model, JSON_SYSTEM, JSON_USER, think=False)
            tps2 = jm["eval_tokens"] / jm["eval_s"] if jm["eval_s"] else 0
            print(
                f"[json] {jdt:.1f}s (load {jm['load_s']}s), "
                f"{jm['eval_tokens']} ток. @ {tps2:.1f} т/с"
            )
            probe = jtext.strip()
            if probe.startswith("```"):
                probe = probe.split("```")[1].lstrip("json").strip()
            parsed = json.loads(probe)
            ideas = parsed.get("ideas") if isinstance(parsed, dict) else None
            ok_json = isinstance(ideas, list) and len(ideas) >= 1
            print(f"[json] парсится: {ok_json}; сырой ответ: {jtext.strip()[:400]}")
        except Exception as e:
            print(f"[json] ОШИБКА: {e}")
            jdt = 0
            tps2 = 0
        report.append(
            {"model": model, "style_s": round(dt, 1), "style_tps": round(tps, 1),
             "json_s": round(jdt, 1), "json_tps": round(tps2, 1), "json_ok": ok_json}
        )
    Path("logs").mkdir(exist_ok=True)
    (Path("logs") / "bakeoff_brain.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

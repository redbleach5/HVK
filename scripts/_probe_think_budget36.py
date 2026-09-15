# -*- coding: utf-8 -*-
"""qwen3.6: хватает ли продакшен-бюджета (num_predict) на мысль и ответ.

Матрица: num_predict 4500 (как в клиенте: 2500 мысль + 2000 ответ),
и вариант с reasoning_effort=low — думает короче?
"""
import json
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API = "http://127.0.0.1:11434/api/chat"
QUESTION = (
    "сил мало, а хочется что-то тёплое выложить. что посоветуешь?"
    " (короткий ответ, 2-3 предложения, с «почему»)"
)


def run(label: str, extra: dict) -> None:
    payload = {
        "model": "qwen3.6:latest",
        "messages": [{"role": "user", "content": QUESTION}],
        "stream": False,
        "think": True,
        "keep_alive": "30m",
        "options": {"num_ctx": 8192, "num_predict": 4500, "temperature": 0.6},
    }
    payload.update(extra)
    req = urllib.request.Request(
        API,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    import time

    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    dt = time.perf_counter() - t0
    msg = data.get("message") or {}
    thinking = msg.get("thinking") or ""
    content = msg.get("content") or ""
    print(
        f"[{label}] {dt:.0f}s; мысль {len(thinking)} симв; ответ {len(content)} симв; "
        f"done={data.get('done_reason')}"
    )
    print("   ответ:", " ".join(content.split())[:200])


run("num_predict=4500", {})
run("num_predict=4500 + effort low", {"reasoning_effort": "low"})

# -*- coding: utf-8 -*-
"""qwen3.6: think=false — пустой ли thinking и чистый ли контент."""
import json
import sys
import time
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API = "http://127.0.0.1:11434/api/chat"
payload = {
    "model": "qwen3.6:latest",
    "messages": [
        {"role": "system", "content": "Отвечай только валидным JSON без markdown."},
        {"role": "user", "content": 'Верни JSON: {"ok": true, "n": 2} и ничего больше.'},
    ],
    "stream": False,
    "think": False,
    "options": {"num_ctx": 4096},
}
req = urllib.request.Request(
    API,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
t0 = time.perf_counter()
with urllib.request.urlopen(req, timeout=300) as r:
    data = json.loads(r.read().decode("utf-8"))
msg = data.get("message") or {}
content = msg.get("content") or ""
thinking = msg.get("thinking")
print(f"время: {time.perf_counter() - t0:.1f}s")
print(f"thinking поле: {repr(thinking)[:120]}")
print(f"<think> в контенте: {'<think>' in content}")
print(f"контент ({len(content)} симв.): {content[:200]}")
try:
    parsed = json.loads(content.strip())
    print(f"JSON парсится: {bool(parsed)}")
except Exception as e:
    print(f"JSON не парсится: {e}")

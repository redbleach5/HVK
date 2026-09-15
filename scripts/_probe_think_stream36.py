# -*- coding: utf-8 -*-
"""qwen3.6 в стриме: thinking отдельным полем, контент чистый?"""
import json
import re
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

API = "http://127.0.0.1:11434/api/chat"
payload = {
    "model": "qwen3.6:latest",
    "messages": [
        {"role": "user", "content": "Одной фразой: почему полезно медленное утро?"},
    ],
    "stream": True,
    "think": True,
    "options": {"num_ctx": 4096},
}
req = urllib.request.Request(
    API,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
_THINK_TAG = re.compile(r"<\s*/?\s*think", re.IGNORECASE)
think_chars = 0
text_chars = 0
bad_content_think = False
with urllib.request.urlopen(req, timeout=300) as r:
    for raw in r:
        if not raw.strip():
            continue
        chunk = json.loads(raw.decode("utf-8"))
        msg = chunk.get("message") or {}
        t = msg.get("thinking") or ""
        c = msg.get("content") or ""
        think_chars += len(t)
        text_chars += len(c)
        if c and _THINK_TAG.search(c):
            bad_content_think = True
print(f"thinking симв: {think_chars}")
print(f"content симв: {text_chars}")
print(f"теги мысли в контенте: {bad_content_think}")
ok = think_chars > 0 and not bad_content_think and text_chars > 0
print("ОК: размышляю отдельным полем" if ok else "ПРОВАЛ: мысли попали в контент")
sys.exit(0 if ok else 1)


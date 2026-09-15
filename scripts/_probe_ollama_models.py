# -*- coding: utf-8 -*-
"""Список моделей Ollama с размерами и квантизацией (без запуска модели)."""
import json
import sys
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

URL = "http://127.0.0.1:11434/api/tags"

with urllib.request.urlopen(URL, timeout=10) as r:
    data = json.loads(r.read().decode("utf-8"))

models = data.get("models", [])
print(f"моделей в Ollama: {len(models)}")
for m in models:
    name = m.get("name", "?")
    size_gb = (m.get("size") or 0) / 1e9
    details = m.get("details") or {}
    fam = details.get("family", "?")
    quant = details.get("quantization_level", "?")
    params = details.get("parameter_size", "?")
    print(f"  {name:45s} {size_gb:6.1f} ГБ  {fam:12s} {params:9s} {quant}")

Path("logs").mkdir(exist_ok=True)
(Path("logs") / "ollama_models.json").write_text(
    json.dumps(models, ensure_ascii=False, indent=2), encoding="utf-8"
)
print("\nподробности: logs/ollama_models.json")

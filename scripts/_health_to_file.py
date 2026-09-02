# -*- coding: utf-8 -*-
"""Пишет ответ /health в logs/f_health.log (для чтения без shell integration)."""
import httpx

resp = httpx.get("http://127.0.0.1:8080/health", timeout=8)
with open(r"C:\HVK\logs\f_health.log", "w", encoding="utf-8") as fh:
    fh.write(f"status={resp.status_code}\n{resp.text}\n")
print("HEALTH_WRITTEN")

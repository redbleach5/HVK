# -*- coding: utf-8 -*-
"""API-проверка продукта. Вкладка стола — GET /desk, не query-string."""
from __future__ import annotations

import json
from pathlib import Path

import httpx

ROOT = Path(r"C:\HVK")
API = "http://127.0.0.1:8080"
OUT = ROOT / "scripts" / "_verify_ui.json"

_DESKS = (
    "Чат",
    "Сегодня",
    "Фото",
    "Текст",
    "Идеи и план",
    "Аналитика",
    "ЛС",
)


def _get(client: httpx.Client, path: str, **params):
    r = client.get(path, params=params or None)
    return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text


def api_pass() -> dict:
    report: dict = {"ok": True, "checks": []}
    timeout = httpx.Timeout(60.0, connect=10.0)
    with httpx.Client(base_url=API, timeout=timeout) as client:
        for path, params in (
            ("/health", {}),
            ("/onboarding/status", {}),
            ("/voice", {}),
            ("/today", {}),
            ("/ideas", {}),
            ("/plan", {}),
            ("/analytics", {"with_report": "false"}),
            ("/chat/history", {}),
            ("/rhythm/hint", {}),
            ("/desk", {}),
        ):
            try:
                code, body = _get(client, path, **params)
            except Exception as exc:
                report["ok"] = False
                report["checks"].append({"path": path, "error": str(exc)})
                continue
            item: dict = {"path": path, "status": code}
            if code >= 400:
                report["ok"] = False
                item["body"] = str(body)[:400]
            elif path == "/onboarding/status" and isinstance(body, dict):
                item["posts"] = body.get("posts_imported")
                item["voice_ready"] = body.get("voice_ready")
                item["done"] = body.get("done")
                if int(body.get("posts_imported") or 0) < 2:
                    report["ok"] = False
                    item["problem"] = "archive too small"
            elif path == "/today" and isinstance(body, dict):
                digest = body.get("digest") or ""
                item["digest_chars"] = len(digest)
                item["ideas"] = len(body.get("ideas") or [])
                if "не читала твои тексты" in digest or "угадайка" in digest:
                    report["ok"] = False
                    item["problem"] = "today still empty-archive copy"
            elif path == "/voice" and isinstance(body, dict):
                p = body.get("profile") or {}
                item["has_tone"] = bool(p.get("tone"))
                item["shades"] = list((p.get("shades") or {}).keys())
            elif path == "/analytics" and isinstance(body, dict):
                item["posts_count"] = body.get("posts_count")
                item["series"] = len(body.get("series") or [])
                item["has_report"] = bool(body.get("report"))
            elif path == "/chat/history" and isinstance(body, dict):
                item["messages"] = len(body.get("messages") or [])
            elif path == "/ideas" and isinstance(body, dict):
                item["ideas"] = len(body.get("ideas") or [])
            elif path == "/plan" and isinstance(body, list):
                item["items"] = len(body)
            elif path == "/desk" and isinstance(body, dict):
                item["desk"] = body.get("desk")
                if body.get("desk") not in _DESKS:
                    report["ok"] = False
                    item["problem"] = "unknown desk"
            report["checks"].append(item)
    return report


def main() -> None:
    report = api_pass()
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    print("ok" if report["ok"] else "FAIL")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""Smoke: SPA собран, :8501 отдаёт HTML, API health ok."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist" / "index.html"
OUT = ROOT / "scripts" / "_verify_frontend.json"


def main() -> int:
    report: dict = {"ok": True, "checks": []}

    if not DIST.is_file():
        report["ok"] = False
        report["checks"].append({"build": "missing", "path": str(DIST)})
    else:
        report["checks"].append({
            "build": "ok",
            "assets": len(list((ROOT / "frontend" / "dist" / "assets").glob("*.js"))),
        })

    try:
        ui = httpx.get("http://127.0.0.1:8501/", timeout=5.0)
        report["checks"].append({"ui": ui.status_code, "html": "<!doctype html" in ui.text.lower()})
        if ui.status_code != 200 or "<!doctype html" not in ui.text.lower():
            report["ok"] = False
    except Exception as exc:
        report["ok"] = False
        report["checks"].append({"ui": "error", "detail": str(exc)})

    try:
        api = httpx.get("http://127.0.0.1:8080/health", timeout=5.0)
        report["checks"].append({"api": api.status_code})
        if api.status_code != 200:
            report["ok"] = False
    except Exception as exc:
        report["ok"] = False
        report["checks"].append({"api": "error", "detail": str(exc)})

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    print("ok" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

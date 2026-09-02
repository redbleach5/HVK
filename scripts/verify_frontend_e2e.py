# -*- coding: utf-8 -*-
"""Playwright smoke: SPA на :8501, прокси /api, навигация по столу."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist" / "index.html"
OUT = ROOT / "scripts" / "_verify_frontend_e2e.json"
PLAYWRIGHT_JSON = FRONTEND / "playwright-report" / "results.json"


def _npm_cmd() -> str:
    return shutil.which("npm") or "npm"


def main() -> int:
    report: dict = {"ok": True, "checks": []}

    if not DIST.is_file():
        report["ok"] = False
        report["checks"].append({"build": "missing", "path": str(DIST)})
    else:
        report["checks"].append({"build": "ok"})

    for name, url in (("ui", "http://127.0.0.1:8501/"), ("api", "http://127.0.0.1:8080/health")):
        try:
            r = httpx.get(url, timeout=5.0)
            report["checks"].append({name: r.status_code})
            if r.status_code != 200:
                report["ok"] = False
        except Exception as exc:
            report["ok"] = False
            report["checks"].append({name: "error", "detail": str(exc)})

    if not report["ok"]:
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", OUT)
        print("FAIL (precheck)")
        return 1

    npm = _npm_cmd()
    install = subprocess.run(
        [npm, "exec", "--", "playwright", "install", "chromium"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if install.returncode != 0:
        report["ok"] = False
        report["checks"].append(
            {"playwright_install": install.returncode, "stderr": (install.stderr or "")[-500:]},
        )
        OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", OUT)
        print("FAIL (playwright install)")
        return 1

    run_smoke = subprocess.run(
        [npm, "run", "test:e2e:smoke"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    report["checks"].append({"playwright_smoke_exit": run_smoke.returncode})
    run = run_smoke
    if run_smoke.returncode != 0:
        report["ok"] = False
        tail = (run_smoke.stdout or "") + "\n" + (run_smoke.stderr or "")
        report["checks"].append({"playwright_smoke_log_tail": tail[-1500:]})
    else:
        run = subprocess.run(
            [npm, "run", "test:e2e:model:fast"],
            cwd=FRONTEND,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
        )
        report["checks"].append({"playwright_model_fast_exit": run.returncode})
        if run.returncode != 0:
            report["ok"] = False
            tail = (run.stdout or "") + "\n" + (run.stderr or "")
            report["checks"].append({"playwright_model_fast_log_tail": tail[-2000:]})

    if PLAYWRIGHT_JSON.is_file():
        try:
            pw = json.loads(PLAYWRIGHT_JSON.read_text(encoding="utf-8"))
            stats = pw.get("stats") or {}
            report["checks"].append(
                {
                    "tests": stats.get("expected", 0),
                    "passed": stats.get("expected", 0) - stats.get("unexpected", 0) - stats.get("skipped", 0),
                    "skipped": stats.get("skipped", 0),
                    "failed": stats.get("unexpected", 0),
                },
            )
        except Exception as exc:
            report["checks"].append({"playwright_json": str(exc)})

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    print("ok" if report["ok"] else "FAIL")
    if not report["ok"] and run.stdout:
        print(run.stdout[-1500:])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

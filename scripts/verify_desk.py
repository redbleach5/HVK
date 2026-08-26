# -*- coding: utf-8 -*-
"""Стол: вкладка и черновик живут в профиле, переживают перезапуск UI."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8080"
OUT = ROOT / "scripts" / "_verify_desk.json"
MARKER = "черновик-проверки-стола"


def main() -> int:
    db = ROOT / "data" / "app.db"
    conn = sqlite3.connect(str(db))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(author_profile)").fetchall()}
    conn.close()
    needed = {"desk", "draft_text", "open_plan_item_id"}
    missing = sorted(needed - cols)
    report: dict = {"ok": True, "columns_missing": missing, "steps": []}
    if missing:
        report["ok"] = False

    timeout = httpx.Timeout(20.0, connect=5.0)
    with httpx.Client(base_url=API, timeout=timeout) as client:
        before = client.get("/desk")
        report["steps"].append({"get_before": before.status_code, "body": before.json()})
        if before.status_code != 200:
            report["ok"] = False
            OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print("wrote", OUT)
            return 1

        original = before.json()
        patched = client.patch(
            "/desk",
            json={"desk": "Текст", "draft_text": MARKER, "plan_item_id": None},
        )
        report["steps"].append({"patch": patched.status_code, "body": patched.json()})
        if patched.status_code != 200:
            report["ok"] = False

        after = client.get("/desk")
        body = after.json()
        report["steps"].append({"get_after": after.status_code, "body": body})
        if body.get("desk") != "Текст" or body.get("draft_text") != MARKER:
            report["ok"] = False
            report["problem"] = "patch did not stick"

        bad = client.patch("/desk", json={"desk": "not-a-tab"})
        report["steps"].append({"patch_bad": bad.status_code, "body": bad.text[:200]})
        if bad.status_code != 400:
            report["ok"] = False
            report["bad_desk_problem"] = "expected 400 for unknown tab"

        restore = client.patch(
            "/desk",
            json={
                "desk": original.get("desk") or "Чат",
                "draft_text": original.get("draft_text") or "",
                "plan_item_id": original.get("plan_item_id"),
            },
        )
        restored = client.get("/desk").json()
        report["steps"].append({"restore": restore.status_code, "body": restored})
        if restored.get("desk") != (original.get("desk") or "Чат"):
            report["ok"] = False
            report["restore_problem"] = "did not restore original desk"
        if restored.get("draft_text") == MARKER:
            report["ok"] = False
            report["restore_problem"] = "test draft left in profile"

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    print("ok" if report["ok"] else "FAIL")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

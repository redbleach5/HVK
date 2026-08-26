"""Проверка VK: без /health (он долго пингует модели). Токены не печатает."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.vk.client import is_configured

API = "http://127.0.0.1:8080"


def main() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    token = (settings.vk_token or "").strip()
    owner = (settings.vk_owner_id or "").strip()
    report: dict = {
        "token_set": bool(token),
        "token_len": len(token),
        "owner_set": bool(owner),
        "is_configured": is_configured(),
        "owner_negative": False,
    }
    if owner:
        try:
            report["owner_negative"] = int(owner) < 0
        except ValueError:
            report["owner_parse"] = "bad"

    with httpx.Client(base_url=API, timeout=20.0) as c:
        status = c.get("/onboarding/status")
        report["onboarding"] = {
            "status": status.status_code,
            "posts": status.json().get("posts_imported"),
            "voice_ready": status.json().get("voice_ready"),
        }
        inbox = c.get("/concierge/inbox", params={"limit": 5})
        data = inbox.json()
        report["inbox"] = {
            "status": inbox.status_code,
            "available": data.get("available"),
            "n": len(data.get("items") or []),
            "message": (data.get("message") or "")[:160],
        }
        wall = c.post("/onboarding/import-vk")
        body = wall.json()
        report["import_vk"] = {
            "status": wall.status_code,
            "detail": body.get("detail")
            or f"posts={body.get('posts_imported')}",
        }

    out = ROOT / "scripts" / "_tmp_vk_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)
    print("token_set", report["token_set"], "configured", report["is_configured"])
    print("inbox", report["inbox"])
    print("import_vk", report["import_vk"]["status"], report["import_vk"]["detail"][:120])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

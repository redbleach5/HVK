"""Какие методы VK живы с текущим токеном. Значения токена не печатает."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.vk.client import _call, _owner_id


async def _try(name: str, **params) -> dict:
    try:
        data = await _call(name, **params)
        if isinstance(data, dict):
            n = len(data.get("items") or data.get("groups") or [])
            keys = list(data.keys())[:6]
        elif isinstance(data, list):
            n = len(data)
            keys = ["list"]
        else:
            n = 0
            keys = [type(data).__name__]
        return {"ok": True, "n": n, "keys": keys}
    except Exception as exc:
        text = str(exc)
        code = ""
        if text.startswith("[") and "]" in text:
            code = text[1 : text.index("]")]
        return {"ok": False, "code": code, "error": text[:180]}


async def main() -> None:
    get_settings.cache_clear()
    owner = _owner_id()
    gid = abs(owner)
    report = {
        "owner_negative": owner < 0,
        "methods": {
            "groups.getById": await _try("groups.getById", group_id=gid, fields="members_count"),
            "messages.getConversations": await _try(
                "messages.getConversations", count=5, filter="all", group_id=gid
            ),
            "wall.get": await _try("wall.get", owner_id=owner, count=1, filter="owner"),
            "wall.getById": await _try("wall.getById", posts=f"{owner}_1"),
            "photos.getWallUploadServer": await _try(
                "photos.getWallUploadServer", group_id=gid
            ),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

"""Рабочий набор диалога: нужные посты копятся, пока разговор жив."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from app.config import get_settings
from app.db.models import Post

logger = logging.getLogger(__name__)

_MAX_ITEMS = 8
_TEXT_CAP = 1600


def _path():
    settings = get_settings()
    folder = settings.resolve_path(settings.desk_path)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "working.json"


def clear_working() -> None:
    """Сброс при очистке чата."""
    path = _path()
    if path.exists():
        path.unlink()


def remember_posts(posts: list[Post], *, reason: str = "") -> None:
    """Добавляет найденные посты в набор этого диалога."""
    if not posts:
        return
    data = _load()
    by_id: dict[int, dict[str, Any]] = {
        int(item["post_id"]): item for item in data if item.get("post_id")
    }
    now = datetime.now().isoformat(timespec="seconds")
    why = " ".join((reason or "").split())[:160]
    for post in posts:
        text = " ".join((post.text or "").split())
        if len(text) > _TEXT_CAP:
            text = text[:_TEXT_CAP].rstrip() + "…"
        date = post.published_at.strftime("%d.%m") if post.published_at else "без даты"
        by_id[post.id] = {
            "post_id": post.id,
            "theme": post.theme or "",
            "date": date,
            "engagement": float(post.engagement or 0),
            "text": text,
            "reason": why,
            "touched_at": now,
        }
    items = sorted(by_id.values(), key=lambda row: row.get("touched_at") or "", reverse=True)
    _save(items[:_MAX_ITEMS])


def working_post_ids() -> list[int]:
    """Номера постов, уже открытых в этом диалоге."""
    ids: list[int] = []
    seen: set[int] = set()
    for item in _load():
        pid = int(item.get("post_id") or 0)
        if not pid or pid in seen:
            continue
        seen.add(pid)
        ids.append(pid)
    return ids


def working_prompt(*, exclude: set[int] | None = None) -> str:
    """Тексты, уже открытые в этом диалоге, кроме тех, что в текущей выборке."""
    skip = exclude or set()
    lines: list[str] = []
    for item in _load():
        pid = int(item.get("post_id") or 0)
        if pid in skip:
            continue
        text = (item.get("text") or "").strip()
        if not text:
            continue
        theme = item.get("theme") or "жизнь"
        date = item.get("date") or "без даты"
        lines.append(f"— {date}, «{theme}», пост #{pid}: {text}")
    return "\n".join(lines)


def _load() -> list[dict[str, Any]]:
    path = _path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Рабочий набор диалога не прочитался — начну заново")
        return []
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    return []


def _save(items: list[dict[str, Any]]) -> None:
    path = _path()
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

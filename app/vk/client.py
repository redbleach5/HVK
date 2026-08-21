"""Клиент VK: импорт постов, статистика, отложенный постинг с подтверждением."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import PlanItem, Post
from app.memory.chroma import upsert_post
from app.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class VkNotConfiguredError(Exception):
    """Токен или owner_id не заданы в .env."""

    user_message = "VK ещё не подключён — токен спрятан в настройках под капотом."


class VkConfirmRequiredError(Exception):
    """Попытка опубликовать без явного confirm=True."""

    user_message = "Публикация только после явного подтверждения."


class VkMessagesUnavailableError(Exception):
    """Нет прав на чтение ЛС сообщества."""

    user_message = "Пока не вижу входящие ЛС — можно вставить сообщение вручную 🤍"


class RateLimiter:
    """Простой лимитер: не чаще одного запроса в interval секунд."""

    def __init__(self, interval: float = 0.4) -> None:
        self.interval = interval
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = self.interval - (now - self._last)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = time.monotonic()


_limiter = RateLimiter(0.4)


def _engagement(likes: int, comments: int, reposts: int, views: int) -> float:
    """Грубая метрика вовлечённости для сортировок."""
    base = likes * 1.0 + comments * 2.5 + reposts * 3.0
    if views > 0:
        return base + min(views / 100.0, 50.0)
    return base


def _owner_id() -> int:
    settings = get_settings()
    if not settings.vk_token or not settings.vk_owner_id:
        raise VkNotConfiguredError()
    return int(settings.vk_owner_id)


def _sync_api():
    """Создаёт синхронный vk_api.Api (вызывать из to_thread)."""
    import vk_api

    settings = get_settings()
    session = vk_api.VkApi(token=settings.vk_token)
    return session.get_api()


def _sync_vk_session():
    """Синхронная VkApi-сессия для upload."""
    import vk_api

    settings = get_settings()
    return vk_api.VkApi(token=settings.vk_token)


async def _call(method: str, **params: Any) -> Any:
    """Вызов VK API с rate limit через asyncio.to_thread."""
    await _limiter.wait()

    def _run() -> Any:
        api = _sync_api()
        return getattr(api, method)(**params)

    return await asyncio.to_thread(_run)


def _photo_urls_from_attachments(attachments: list[dict[str, Any]] | None) -> list[str]:
    urls: list[str] = []
    for att in attachments or []:
        if att.get("type") != "photo":
            continue
        photo = att.get("photo") or {}
        sizes = photo.get("sizes") or []
        if not sizes:
            continue
        best = max(sizes, key=lambda s: s.get("width", 0) * s.get("height", 0))
        url = best.get("url")
        if url:
            urls.append(url)
    return urls


async def import_wall_posts(
    session: AsyncSession,
    *,
    count: int = 50,
    with_comments: bool = True,
) -> int:
    """Тянет посты со стены в SQLite и Chroma. Возвращает число импортированных/обновлённых."""
    owner = _owner_id()
    response = await _call("wall.get", owner_id=owner, count=min(count, 100), filter="owner")
    items = response.get("items") or []
    imported = 0

    for item in items:
        if item.get("post_type") == "postpone" or item.get("is_pinned") and not item.get("text"):
            pass
        vk_id = f"{owner}_{item['id']}"
        text = (item.get("text") or "").strip()
        likes = int((item.get("likes") or {}).get("count") or 0)
        comments_count = int((item.get("comments") or {}).get("count") or 0)
        reposts = int((item.get("reposts") or {}).get("count") or 0)
        views = int((item.get("views") or {}).get("count") or 0)
        published_at = datetime.utcfromtimestamp(item["date"]) if item.get("date") else None
        photo_urls = _photo_urls_from_attachments(item.get("attachments"))

        comments: list[dict[str, Any]] = []
        if with_comments and comments_count > 0:
            try:
                comments = await _fetch_comments(owner, int(item["id"]))
            except Exception:
                logger.debug("Не удалось взять комментарии к %s", vk_id, exc_info=True)

        result = await session.execute(select(Post).where(Post.vk_post_id == vk_id))
        post = result.scalar_one_or_none()
        if post is None:
            post = Post(vk_post_id=vk_id)
            session.add(post)

        post.text = text
        post.published_at = published_at
        post.likes = likes
        post.comments_count = comments_count
        post.reposts = reposts
        post.views = views
        post.engagement = _engagement(likes, comments_count, reposts, views)
        post.photo_urls = photo_urls
        post.comments = comments
        await session.flush()

        upsert_post(
            post.id,
            text,
            {
                "published_at": published_at.isoformat() if published_at else None,
                "theme": post.theme,
                "engagement": post.engagement,
                "vk_post_id": vk_id,
            },
        )
        imported += 1

    memory = MemoryStore(session)
    await memory.refresh_rhythm()
    await memory.log("vk_import", f"Подтянула {imported} постов из VK")
    await session.commit()
    logger.info("VK import: %s постов", imported)
    return imported


async def _fetch_comments(owner_id: int, post_id: int, limit: int = 20) -> list[dict[str, Any]]:
    response = await _call(
        "wall.getComments",
        owner_id=owner_id,
        post_id=post_id,
        count=limit,
        sort="desc",
        preview_length=0,
    )
    out: list[dict[str, Any]] = []
    for row in response.get("items") or []:
        text = (row.get("text") or "").strip()
        if text:
            out.append(
                {
                    "id": row.get("id"),
                    "text": text[:500],
                    "from_id": row.get("from_id"),
                    "date": row.get("date"),
                }
            )
    return out


async def refresh_stats(session: AsyncSession) -> int:
    """Обновляет лайки/комменты/просмотры у уже известных постов."""
    owner = _owner_id()
    result = await session.execute(
        select(Post).where(Post.vk_post_id.is_not(None)).order_by(Post.id.desc()).limit(40)
    )
    posts = list(result.scalars())
    updated = 0
    for post in posts:
        if not post.vk_post_id or "_" not in post.vk_post_id:
            continue
        _, raw_id = post.vk_post_id.split("_", 1)
        try:
            got = await _call(
                "wall.getById",
                posts=f"{owner}_{raw_id}",
            )
        except Exception:
            logger.debug("stats fail for %s", post.vk_post_id, exc_info=True)
            continue
        items = got if isinstance(got, list) else (got.get("items") or got or [])
        if not items:
            continue
        item = items[0]
        likes = int((item.get("likes") or {}).get("count") or 0)
        comments_count = int((item.get("comments") or {}).get("count") or 0)
        reposts = int((item.get("reposts") or {}).get("count") or 0)
        views = int((item.get("views") or {}).get("count") or 0)
        post.likes = likes
        post.comments_count = comments_count
        post.reposts = reposts
        post.views = views
        post.engagement = _engagement(likes, comments_count, reposts, views)
        updated += 1

    if updated:
        memory = MemoryStore(session)
        await memory.refresh_rhythm()
        await memory.log("vk_stats", f"Обновила статистику у {updated} постов")
    await session.commit()
    return updated


def _resolve_photo_paths(raw_paths: list[str] | None) -> list[Path]:
    """Превращает имена/пути в существующие файлы под uploads."""
    if not raw_paths:
        return []
    settings = get_settings()
    upload_dir = settings.resolve_path(settings.uploads_path)
    resolved: list[Path] = []
    for raw in raw_paths:
        path = Path(raw)
        if not path.is_absolute():
            path = upload_dir / path
        if path.exists() and path.is_file():
            resolved.append(path)
        else:
            logger.warning("Фото для поста не найдено: %s", raw)
    return resolved


async def _upload_wall_photos(paths: list[Path]) -> tuple[list[str], Optional[str]]:
    """Загружает фото на стену. Возвращает (attachments, warning)."""
    if not paths:
        return [], None
    owner = _owner_id()
    group_id = abs(owner) if owner < 0 else None
    user_id = owner if owner > 0 else None

    def _run() -> list[str]:
        import vk_api

        vk_session = _sync_vk_session()
        upload = vk_api.VkUpload(vk_session)
        saved = upload.photo_wall(
            photos=[str(p) for p in paths],
            user_id=user_id,
            group_id=group_id,
        )
        attachments: list[str] = []
        for photo in saved if isinstance(saved, list) else [saved]:
            owner_photo = photo.get("owner_id")
            photo_id = photo.get("id")
            if owner_photo is not None and photo_id is not None:
                attachments.append(f"photo{owner_photo}_{photo_id}")
        return attachments

    try:
        await _limiter.wait()
        attachments = await asyncio.to_thread(_run)
        return attachments, None
    except Exception:
        logger.exception("Не удалось загрузить фото на стену VK")
        return [], "Текст ушёл, а фото не прикрепились — добавь их вручную в VK 🤍"


async def schedule_post(
    session: AsyncSession,
    *,
    message: str,
    publish_date_unix: Optional[int],
    confirm: bool,
    photo_paths: list[str] | None = None,
    plan_item_id: Optional[int] = None,
) -> dict[str, Any]:
    """Отложенный (или немедленный) постинг только при confirm=True."""
    if not confirm:
        raise VkConfirmRequiredError()
    if not message.strip():
        raise ValueError("пустой текст поста")

    owner = _owner_id()
    paths = _resolve_photo_paths(photo_paths)
    attachments, photos_warning = await _upload_wall_photos(paths)

    params: dict[str, Any] = {
        "owner_id": owner,
        "from_group": 1 if owner < 0 else 0,
        "message": message,
    }
    if publish_date_unix:
        params["publish_date"] = int(publish_date_unix)
    if attachments:
        params["attachments"] = ",".join(attachments)

    result = await _call("wall.post", **params)
    post_id = result.get("post_id")
    vk_post_id = f"{owner}_{post_id}"

    local = Post(
        vk_post_id=vk_post_id,
        text=message.strip(),
        published_at=datetime.utcnow()
        if not publish_date_unix
        else datetime.utcfromtimestamp(int(publish_date_unix)),
        photo_urls=[],
        plan_item_id=plan_item_id,
    )
    session.add(local)
    await session.flush()

    if plan_item_id:
        item = await session.get(PlanItem, plan_item_id)
        if item is not None:
            item.status = "published"
            item.published_post_id = local.id
            item.draft_text = message.strip()

    memory = MemoryStore(session)
    await memory.log(
        "publish",
        "Отложила пост в VK" if publish_date_unix else "Опубликовала пост в VK",
        {"vk_post_id": vk_post_id, "photos": len(attachments)},
    )
    await session.commit()
    return {
        "ok": True,
        "vk_post_id": vk_post_id,
        "post_id": post_id,
        "plan_item_id": plan_item_id,
        "local_post_id": local.id,
        "photos_attached": len(attachments),
        "photos_warning": photos_warning,
    }


async def fetch_inbox(limit: int = 15) -> dict[str, Any]:
    """Последние диалоги сообщества. Без автоответов."""
    owner = _owner_id()
    params: dict[str, Any] = {
        "count": min(max(limit, 1), 20),
        "extended": 0,
        "filter": "all",
    }
    if owner < 0:
        params["group_id"] = abs(owner)

    try:
        response = await _call("messages.getConversations", **params)
    except Exception as exc:
        logger.info("Inbox недоступен: %s", exc)
        raise VkMessagesUnavailableError() from exc

    items_out: list[dict[str, Any]] = []
    for row in response.get("items") or []:
        conversation = row.get("conversation") or {}
        peer = conversation.get("peer") or {}
        last = row.get("last_message") or {}
        text = (last.get("text") or "").strip()
        if not text and last.get("attachments"):
            text = "[вложение]"
        date_raw = last.get("date")
        date_iso = (
            datetime.utcfromtimestamp(date_raw).isoformat() if date_raw else None
        )
        items_out.append(
            {
                "peer_id": int(peer.get("id") or last.get("peer_id") or 0),
                "preview": text[:280] or "пустое сообщение",
                "date": date_iso,
                "unread": int(conversation.get("unread_count") or 0),
            }
        )

    return {
        "items": items_out,
        "available": True,
        "message": "",
    }


def is_configured() -> bool:
    """Есть ли токен и owner в настройках."""
    settings = get_settings()
    return bool(settings.vk_token and settings.vk_owner_id)

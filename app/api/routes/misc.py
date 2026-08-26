"""Аналитика, архив, консьерж, фидбек, публикация."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.archive import find_similar, search_archive, seasonal_reuse_suggestions
from app.agents.audience import analyze_audience
from app.agents.concierge import draft_dm_reply
from app.api.errors import not_found
from app.config import get_settings
from app.db.session import get_session
from app.memory.feedback import apply_feedback
from app.memory.store import MemoryStore
from app.schemas.agents import ArchiveSearchResult, AudienceReport, ConciergeReply
from app.schemas.api import (
    ALLOWED_DESKS,
    AnalyticsOut,
    ConciergeIn,
    DeskIn,
    DeskOut,
    InboxItem,
    InboxOut,
    PublishIn,
    PublishOut,
    RhythmHintOut,
)
from app.schemas.common import SuggestionFeedback
from app.vk.client import (
    VkMessagesUnavailableError,
    fetch_inbox,
    schedule_post,
)


async def _do_publish(
    session: AsyncSession,
    *,
    message: str,
    publish_date_unix: Optional[int],
    confirm: bool,
    photo_paths: list[str],
    plan_item_id: Optional[int],
) -> PublishOut:
    try:
        result = await schedule_post(
            session,
            message=message,
            publish_date_unix=publish_date_unix,
            confirm=confirm,
            photo_paths=photo_paths,
            plan_item_id=plan_item_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "Пустой текст поста") from exc
    return PublishOut(
        ok=True,
        vk_post_id=result.get("vk_post_id") or "",
        post_id=result.get("local_post_id"),
        plan_item_id=result.get("plan_item_id"),
        photos_attached=int(result.get("photos_attached") or 0),
        photos_warning=result.get("photos_warning"),
    )

router = APIRouter(tags=["misc"])


def _desk_out(profile) -> DeskOut:
    desk = profile.desk if profile.desk in ALLOWED_DESKS else "Чат"
    return DeskOut(
        desk=desk,
        draft_text=profile.draft_text or "",
        plan_item_id=profile.open_plan_item_id,
    )


@router.get("/desk", response_model=DeskOut)
async def get_desk(session: AsyncSession = Depends(get_session)) -> DeskOut:
    profile = await MemoryStore(session).get_profile()
    return _desk_out(profile)


@router.patch("/desk", response_model=DeskOut)
async def patch_desk(
    body: DeskIn,
    session: AsyncSession = Depends(get_session),
) -> DeskOut:
    profile = await MemoryStore(session).get_profile()
    if body.desk is not None:
        if body.desk not in ALLOWED_DESKS:
            raise HTTPException(status_code=400, detail="Нет такой вкладки")
        profile.desk = body.desk
    if body.draft_text is not None:
        profile.draft_text = body.draft_text
    if "plan_item_id" in body.model_fields_set:
        profile.open_plan_item_id = body.plan_item_id
    await session.commit()
    return _desk_out(profile)


@router.get("/analytics", response_model=AnalyticsOut)
async def analytics(
    with_report: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsOut:
    memory = MemoryStore(session)
    posts = await memory.recent_posts(40)
    top = await memory.top_posts(90, 8)

    series = []
    for post in reversed(posts):
        if not post.published_at:
            continue
        series.append(
            {
                "date": post.published_at.date().isoformat(),
                "engagement": post.engagement,
                "likes": post.likes,
                "comments": post.comments_count,
                "views": post.views,
                "theme": post.theme or "",
            }
        )

    top_posts = [
        {
            "id": p.id,
            "theme": p.theme,
            "text": (p.text or "")[:200],
            "engagement": p.engagement,
            "likes": p.likes,
            "comments": p.comments_count,
            "published_at": p.published_at.isoformat() if p.published_at else None,
        }
        for p in top
    ]

    report: AudienceReport | None = None
    if with_report and await memory.count_posts() > 0:
        report = await analyze_audience(session)

    return AnalyticsOut(
        series=series,
        top_posts=top_posts,
        report=report,
        posts_count=await memory.count_posts(),
    )


@router.post("/feedback/{suggestion_id}")
async def feedback(
    suggestion_id: int,
    body: SuggestionFeedback,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        suggestion = await apply_feedback(session, suggestion_id, body.accepted, body.note)
    except KeyError as exc:
        raise not_found(exc.args[0] if exc.args else "Не нашла") from exc
    return {"ok": True, "status": suggestion.status, "id": suggestion.id}


@router.get("/archive/search", response_model=ArchiveSearchResult)
async def archive_search(
    q: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),
) -> ArchiveSearchResult:
    return await search_archive(session, q)


@router.get("/archive/similar/{post_id}", response_model=ArchiveSearchResult)
async def archive_similar(
    post_id: int,
    session: AsyncSession = Depends(get_session),
) -> ArchiveSearchResult:
    return await find_similar(session, post_id)


@router.get("/archive/seasonal", response_model=ArchiveSearchResult)
async def archive_seasonal(
    session: AsyncSession = Depends(get_session),
) -> ArchiveSearchResult:
    return await seasonal_reuse_suggestions(session)


@router.post("/concierge", response_model=ConciergeReply)
async def concierge(
    body: ConciergeIn,
    session: AsyncSession = Depends(get_session),
) -> ConciergeReply:
    return await draft_dm_reply(session, body.message_text)


@router.get("/concierge/inbox", response_model=InboxOut)
async def concierge_inbox(
    limit: int = Query(default=15, ge=1, le=20),
) -> InboxOut:
    """Последние диалоги ЛС. Без автоответов."""
    try:
        raw = await fetch_inbox(limit=limit)
    except VkMessagesUnavailableError as exc:
        return InboxOut(items=[], available=False, message=exc.user_message)
    items = [InboxItem.model_validate(row) for row in raw.get("items") or []]
    return InboxOut(items=items, available=True, message="")


@router.get("/rhythm/hint", response_model=RhythmHintOut)
async def rhythm_hint(session: AsyncSession = Depends(get_session)) -> RhythmHintOut:
    hint = await MemoryStore(session).rhythm_hint()
    return RhythmHintOut(hint=hint)


async def _save_upload_files(files: list[UploadFile]) -> list[str]:
    settings = get_settings()
    upload_dir = settings.resolve_path(settings.uploads_path)
    upload_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for upload in files:
        if not upload.filename:
            continue
        suffix = Path(upload.filename).suffix or ".jpg"
        dest = upload_dir / f"{uuid.uuid4().hex}{suffix}"
        data = await upload.read()
        if not data:
            continue
        dest.write_bytes(data)
        paths.append(str(dest))
    return paths


@router.post("/publish", response_model=PublishOut)
async def publish_json(
    body: PublishIn,
    session: AsyncSession = Depends(get_session),
) -> PublishOut:
    """Публикация текстом (и путями к уже сохранённым фото)."""
    return await _do_publish(
        session,
        message=body.message,
        publish_date_unix=body.publish_date_unix,
        confirm=body.confirm,
        photo_paths=list(body.photo_paths or []),
        plan_item_id=body.plan_item_id,
    )


@router.post("/publish/form", response_model=PublishOut)
async def publish_form(
    session: AsyncSession = Depends(get_session),
    confirm: bool = Form(False),
    message: str = Form(""),
    publish_date_unix: Optional[int] = Form(None),
    plan_item_id: Optional[int] = Form(None),
    files: list[UploadFile] | None = File(default=None),
) -> PublishOut:
    """Публикация из UI с multipart-фото."""
    photo_paths = await _save_upload_files(files or [])
    return await _do_publish(
        session,
        message=message,
        publish_date_unix=publish_date_unix,
        confirm=confirm,
        photo_paths=photo_paths,
        plan_item_id=plan_item_id,
    )

"""Чат — основной способ взаимодействия."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat import (
    clear_chat_history,
    handle_chat,
    idea_to_plan_from_chat,
    iter_chat_ndjson,
    list_chat_history,
)
from app.agents.chat_threads import create_thread, delete_thread, list_threads
from app.agents.router import classify_intent, classify_intent_heuristic
from app.api.errors import not_found
from app.config import get_settings
from app.db.session import SessionLocal, get_session
from app.schemas.api import (
    ChatHistoryOut,
    ChatOut,
    ChatThreadCreateIn,
    ChatThreadOut,
    ChatThreadsOut,
)

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


async def _save_uploads(files: list[UploadFile] | None) -> list[Path]:
    if not files:
        return []
    settings = get_settings()
    upload_dir = settings.resolve_path(settings.uploads_path)
    upload_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for upload in files:
        if not upload.filename:
            continue
        suffix = Path(upload.filename).suffix or ".jpg"
        dest = upload_dir / f"{uuid.uuid4().hex}{suffix}"
        data = await upload.read()
        if not data:
            continue
        dest.write_bytes(data)
        paths.append(dest)
    return paths


def _parse_thread_id(raw: str | int | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@router.get("/threads", response_model=ChatThreadsOut)
async def chat_threads(session: AsyncSession = Depends(get_session)) -> ChatThreadsOut:
    threads = await list_threads(session)
    if not threads:
        created = await create_thread(session)
        threads = [created]
    return ChatThreadsOut(threads=threads)


@router.post("/threads", response_model=ChatThreadOut)
async def chat_thread_create(
    body: ChatThreadCreateIn,
    session: AsyncSession = Depends(get_session),
) -> ChatThreadOut:
    return await create_thread(session, title=body.title)


@router.delete("/threads/{thread_id}")
async def chat_thread_delete(
    thread_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not await delete_thread(session, thread_id):
        raise not_found("Диалог не найден")
    return {"ok": True}


@router.get("/threads/{thread_id}/history", response_model=ChatHistoryOut)
async def chat_thread_history(
    thread_id: int,
    session: AsyncSession = Depends(get_session),
) -> ChatHistoryOut:
    tid, messages = await list_chat_history(session, thread_id=thread_id)
    return ChatHistoryOut(thread_id=tid, messages=messages)


@router.get("/history", response_model=ChatHistoryOut)
async def chat_history(
    session: AsyncSession = Depends(get_session),
    thread_id: int | None = None,
) -> ChatHistoryOut:
    tid, messages = await list_chat_history(session, thread_id=thread_id)
    return ChatHistoryOut(thread_id=tid, messages=messages)


@router.delete("/history")
async def chat_clear(
    session: AsyncSession = Depends(get_session),
    thread_id: int | None = None,
) -> dict:
    tid = await clear_chat_history(session, thread_id=thread_id)
    return {"ok": True, "thread_id": tid}


@router.post("", response_model=ChatOut)
async def chat(
    session: AsyncSession = Depends(get_session),
    message: str = Form(""),
    thread_id: str = Form(""),
    files: list[UploadFile] | None = File(default=None),
) -> ChatOut:
    """Сообщение чата + опциональные фото."""
    paths = await _save_uploads(files)
    if not message.strip() and not paths:
        return ChatOut(reply="Напиши сообщение или прикрепи фото.", intent="help")
    return await handle_chat(
        session,
        message.strip(),
        photo_paths=paths,
        thread_id=_parse_thread_id(thread_id),
    )


@router.post("/stream")
async def chat_stream(
    message: str = Form(""),
    thread_id: str = Form(""),
    files: list[UploadFile] | None = File(default=None),
) -> StreamingResponse:
    """Живой диалог: сначала ход мысли, потом реплика (NDJSON)."""
    paths = await _save_uploads(files)
    text = message.strip()
    tid = _parse_thread_id(thread_id)
    logger.info(
        "chat/stream HTTP thread_id=%s msg_len=%s has_files=%s",
        tid,
        len(text),
        bool(paths),
    )
    if not text and not paths:
        async def _empty():
            yield json.dumps(
                {"t": "done", "reply": "Напиши сообщение или прикрепи фото.", "cards": [], "intent": "help"},
                ensure_ascii=False,
            ) + "\n"

        return StreamingResponse(_empty(), media_type="application/x-ndjson")

    async def _gen():
        yield json.dumps({"t": "open"}, ensure_ascii=False) + "\n"
        async with SessionLocal() as session:
            async for event in iter_chat_ndjson(session, text, photo_paths=paths, thread_id=tid):
                yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(
        _gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/idea/{idea_id}/to-plan", response_model=ChatOut)
async def chat_idea_to_plan(
    idea_id: int,
    session: AsyncSession = Depends(get_session),
) -> ChatOut:
    out = await idea_to_plan_from_chat(session, idea_id)
    if out.reply.startswith("Идея не"):
        raise not_found(out.reply)
    return out


class IntentProbeIn(BaseModel):
    """Запрос для диагностики классификатора интентов."""

    message: str
    has_photos: bool = False


class IntentProbeOut(BaseModel):
    """Результат: интент, источник (heuristic/llm), извлечённые поля."""

    intent: str
    source: str
    draft_text: str = ""
    publish_text: str = ""
    plan_title: str = ""
    confirm_publish: bool = False
    heuristic_guess: str | None = None


@router.post("/intent", response_model=IntentProbeOut)
async def chat_intent_probe(
    body: IntentProbeIn,
    session: AsyncSession = Depends(get_session),
) -> IntentProbeOut:
    """Диагностика: что классификатор решит для данного сообщения."""
    heuristic = classify_intent_heuristic(body.message, has_photos=body.has_photos)
    decision = await classify_intent(session, body.message, has_photos=body.has_photos)
    return IntentProbeOut(
        intent=decision.intent,
        source=decision.source,
        draft_text=decision.draft_text,
        publish_text=decision.publish_text,
        plan_title=decision.plan_title,
        confirm_publish=decision.confirm_publish,
        heuristic_guess=heuristic,
    )

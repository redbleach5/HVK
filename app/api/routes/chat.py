"""Чат — основной способ взаимодействия."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat import (
    clear_chat_history,
    handle_chat,
    idea_to_plan_from_chat,
    iter_chat_ndjson,
    list_chat_history,
)
from app.api.errors import not_found
from app.config import get_settings
from app.db.session import SessionLocal, get_session
from app.schemas.api import ChatHistoryOut, ChatOut

router = APIRouter(prefix="/chat", tags=["chat"])


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


@router.get("/history", response_model=ChatHistoryOut)
async def chat_history(session: AsyncSession = Depends(get_session)) -> ChatHistoryOut:
    messages = await list_chat_history(session)
    return ChatHistoryOut(messages=messages)


@router.delete("/history")
async def chat_clear(session: AsyncSession = Depends(get_session)) -> dict:
    await clear_chat_history(session)
    return {"ok": True}


@router.post("", response_model=ChatOut)
async def chat(
    session: AsyncSession = Depends(get_session),
    message: str = Form(""),
    files: list[UploadFile] | None = File(default=None),
) -> ChatOut:
    """Сообщение чата + опциональные фото."""
    paths = await _save_uploads(files)
    if not message.strip() and not paths:
        return ChatOut(reply="Напиши сообщение или прикрепи фото.", intent="help")
    return await handle_chat(session, message.strip(), photo_paths=paths)


@router.post("/stream")
async def chat_stream(
    message: str = Form(""),
    files: list[UploadFile] | None = File(default=None),
) -> StreamingResponse:
    """Живой диалог: сначала ход мысли, потом реплика (NDJSON)."""
    paths = await _save_uploads(files)
    text = message.strip()
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
            async for event in iter_chat_ndjson(session, text, photo_paths=paths):
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

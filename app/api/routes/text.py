"""Редактура текста и профиль голоса."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.editor import edit_draft
from app.api.errors import not_found
from app.db.models import PlanItem, Suggestion
from app.db.session import get_session
from app.memory.feedback import apply_feedback
from app.memory.store import MemoryStore
from app.schemas.agents import EditorResult
from app.schemas.api import ApplyEditIn, TextEditIn, VoiceProfileOut

router = APIRouter(tags=["text"])


@router.post("/text/edit", response_model=EditorResult)
async def text_edit(
    body: TextEditIn,
    session: AsyncSession = Depends(get_session),
) -> EditorResult:
    """Редактирует черновик с сохранением голоса."""
    result = await edit_draft(session, body.draft, topic_hint=body.topic_hint)
    if body.plan_item_id:
        item = await session.get(PlanItem, body.plan_item_id)
        if item:
            item.draft_text = result.revised_text
            if item.status == "conceived":
                item.status = "written"
            await session.commit()
    return result


@router.post("/text/apply-edit")
async def apply_edit(
    body: ApplyEditIn,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Принимает или отклоняет одну правку и собирает текст."""
    suggestion = await session.get(Suggestion, body.suggestion_id)
    text = body.current_text or ""
    if suggestion is not None:
        payload = suggestion.payload or {}
        original = str(payload.get("original") or "")
        revised = str(payload.get("revised") or "")
        if body.accepted:
            if original and revised and original in text:
                text = text.replace(original, revised, 1)
        elif original and revised and revised in text:
            text = text.replace(revised, original, 1)
    try:
        await apply_feedback(session, body.suggestion_id, body.accepted)
    except KeyError as exc:
        raise not_found(exc.args[0] if exc.args else "Не нашла") from exc
    return {"ok": True, "current_text": text, "accepted": body.accepted}


@router.get("/voice", response_model=VoiceProfileOut)
async def get_voice(session: AsyncSession = Depends(get_session)) -> VoiceProfileOut:
    """Текущий живой профиль голоса."""
    voice = await MemoryStore(session).latest_voice()
    if voice is None:
        raise HTTPException(status_code=404, detail="Профиль голоса ещё не собран")
    return VoiceProfileOut(
        version=voice.version,
        profile=voice.profile or {},
        created_at=voice.created_at.isoformat() if voice.created_at else "",
    )

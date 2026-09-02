"""Идеи и контент-план."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.ideas import generate_ideas, idea_row_to_card
from app.api.errors import not_found
from app.db.models import Idea, PlanItem
from app.db.session import get_session
from app.memory.store import MemoryStore
from app.schemas.agents import IdeaBatch
from app.schemas.api import IdeaGenerateIn, PlanFromTextIn, PlanItemOut, PlanItemUpdate

router = APIRouter(tags=["ideas-plan"])


def _plan_out(item: PlanItem) -> PlanItemOut:
    return PlanItemOut(
        id=item.id,
        idea_id=item.idea_id,
        title=item.title,
        draft_text=item.draft_text or "",
        status=item.status,  # type: ignore[arg-type]
        scheduled_date=item.scheduled_date.date().isoformat() if item.scheduled_date else None,
        published_post_id=item.published_post_id,
    )


@router.get("/ideas", response_model=IdeaBatch)
async def ideas_list(session: AsyncSession = Depends(get_session)) -> IdeaBatch:
    """Последние сохранённые идеи, без генерации."""
    memory = MemoryStore(session)
    rows = await memory.recent_ideas(6)
    return IdeaBatch(ideas=[idea_row_to_card(idea) for idea in rows])


@router.post("/ideas/generate", response_model=IdeaBatch)
async def ideas_generate(
    body: IdeaGenerateIn,
    session: AsyncSession = Depends(get_session),
) -> IdeaBatch:
    return await generate_ideas(session, count=body.count)


@router.post("/ideas/{idea_id}/to-plan", response_model=PlanItemOut)
async def idea_to_plan(
    idea_id: int,
    session: AsyncSession = Depends(get_session),
) -> PlanItemOut:
    """Перетаскивает идею в недельный план."""
    idea = await session.get(Idea, idea_id)
    if idea is None:
        raise not_found("Идея не найдена")
    item = PlanItem(
        idea_id=idea.id,
        title=idea.theme,
        draft_text="",
        status="conceived",
    )
    session.add(item)
    idea.status = "planned"
    await MemoryStore(session).log("plan", f"В план: {idea.theme}")
    await session.commit()
    await session.refresh(item)
    return _plan_out(item)


@router.post("/plan/from-text", response_model=PlanItemOut)
async def plan_from_text(
    body: PlanFromTextIn,
    session: AsyncSession = Depends(get_session),
) -> PlanItemOut:
    """Пункт плана из архива или любой заготовки."""
    title = body.title.strip()[:240]
    item = PlanItem(
        title=title,
        draft_text=body.draft_text.strip(),
        status="conceived",
    )
    session.add(item)
    await MemoryStore(session).log("plan", f"В план из архива: {title}")
    await session.commit()
    await session.refresh(item)
    return _plan_out(item)


@router.get("/plan", response_model=list[PlanItemOut])
async def list_plan(session: AsyncSession = Depends(get_session)) -> list[PlanItemOut]:
    result = await session.execute(select(PlanItem).order_by(PlanItem.id.desc()))
    return [_plan_out(item) for item in result.scalars()]


@router.patch("/plan/{item_id}", response_model=PlanItemOut)
async def update_plan(
    item_id: int,
    body: PlanItemUpdate,
    session: AsyncSession = Depends(get_session),
) -> PlanItemOut:
    item = await session.get(PlanItem, item_id)
    if item is None:
        raise not_found("Пункт плана не найден")
    if body.status is not None:
        item.status = body.status
    if body.draft_text is not None:
        item.draft_text = body.draft_text
    if body.scheduled_date is not None:
        try:
            item.scheduled_date = datetime.fromisoformat(body.scheduled_date)
        except ValueError:
            item.scheduled_date = datetime.strptime(body.scheduled_date, "%Y-%m-%d")
    await session.commit()
    await session.refresh(item)
    return _plan_out(item)


@router.delete("/plan/{item_id}")
async def delete_plan(
    item_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Удаление пункта плана — нужно UI-кнопке «удалить»."""
    item = await session.get(PlanItem, item_id)
    if item is None:
        raise not_found("Пункт плана не найден")
    title = item.title
    await session.delete(item)
    await MemoryStore(session).log("plan", f"Удалён пункт плана: {title}")
    await session.commit()
    return {"ok": True}

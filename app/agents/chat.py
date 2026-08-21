"""Чат-роутер: сохраняет все возможности агентов в одном диалоге."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.archive import seasonal_reuse_suggestions
from app.agents.audience import analyze_audience
from app.agents.base import SYSTEM_ASSISTANT, build_agent_context
from app.agents.concierge import draft_dm_reply
from app.agents.editor import edit_draft
from app.agents.ideas import generate_ideas
from app.agents.photo import analyze_photos
from app.context.engine import current_season, format_date_ru
from app.db.models import ChatMessage, Idea, PlanItem
from app.llm.client import get_llm
from app.llm.exceptions import ModelAsleepError
from app.memory.store import MemoryStore
from app.schemas.api import ChatCard, ChatHistoryItem, ChatOut
from app.vk.client import fetch_inbox, is_configured, schedule_post

logger = logging.getLogger(__name__)

Intent = Literal[
    "today",
    "ideas",
    "analytics",
    "edit",
    "photo",
    "concierge",
    "plan",
    "seasonal",
    "inbox",
    "publish",
    "help",
    "to_plan",
    "general",
]
_VALID_INTENTS = set(get_args(Intent))

_HELP = (
    "Могу в этом чате:\n"
    "· сводку на сегодня\n"
    "· идеи и план\n"
    "· разбор фото (прикрепи файл)\n"
    "· редактуру черновика (вставь текст)\n"
    "· аналитику\n"
    "· черновик ответа на ЛС\n"
    "· сезонный архив\n"
    "· публикацию в VK — только если явно напишешь «опубликовать» и «подтверждаю»\n\n"
    "Кнопки принять/отклонить под карточками — обратная связь для памяти."
)


class _IntentOut(BaseModel):
    intent: str = "general"
    draft_text: str = ""
    publish_text: str = ""
    plan_title: str = ""
    confirm_publish: bool = False


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def classify_intent_heuristic(message: str, *, has_photos: bool) -> Intent | None:
    """Быстрый роутинг без LLM."""
    if has_photos:
        return "photo"
    t = _norm(message)
    if not t:
        return "help"
    if t in {"помощь", "help", "?", "/help"} or t.startswith("что умеешь"):
        return "help"
    if t.startswith("/today") or t in {"сегодня", "сводка", "дайджест"}:
        return "today"
    if t.startswith("/ideas") or t in {"идеи", "идея"} or "предложи идеи" in t:
        return "ideas"
    if t.startswith("/stats") or t in {"аналитика", "статистика", "стата"}:
        return "analytics"
    if t in {"план", "что в плане"} or t.startswith("/plan"):
        return "plan"
    if "сезон" in t and ("архив" in t or "старое" in t or "reuse" in t):
        return "seasonal"
    if t in {"входящие", "inbox", "лс список"} or "входящ" in t:
        return "inbox"
    if "опубликовать" in t or t.startswith("/publish"):
        return "publish"
    if t.startswith("в план") or t.startswith("добавь в план"):
        return "to_plan"
    if any(x in t for x in ("ответь на", "черновик ответа", "это лс", "личное сообщение")):
        return "concierge"
    if len(message.strip()) >= 80 and not t.endswith("?"):
        return "edit"
    return None


async def classify_intent(
    session: AsyncSession,
    message: str,
    *,
    has_photos: bool,
) -> _IntentOut:
    """Определяет намерение: сначала эвристика, иначе LLM."""
    guessed = classify_intent_heuristic(message, has_photos=has_photos)
    if guessed and guessed != "general":
        out = _IntentOut(intent=guessed)
        if guessed == "edit":
            out.draft_text = message.strip()
        if guessed == "publish":
            out.confirm_publish = "подтверждаю" in _norm(message)
            # текст после маркера
            m = re.search(
                r"опубликовать(?:\s+в\s+vk)?\s*:?\s*(.*)$",
                message.strip(),
                flags=re.I | re.S,
            )
            if m:
                out.publish_text = m.group(1).strip()
        if guessed == "to_plan":
            out.plan_title = re.sub(
                r"^(в план|добавь в план)\s*:?\s*",
                "",
                message.strip(),
                flags=re.I,
            ).strip() or message.strip()
        return out

    try:
        context = await build_agent_context(session)
        system = (
            f"{SYSTEM_ASSISTANT}\n"
            "Классифицируй сообщение автора. "
            "intent: today|ideas|analytics|edit|photo|concierge|plan|seasonal|"
            "inbox|publish|help|to_plan|general. "
            "Для edit заполни draft_text. Для publish — publish_text и confirm_publish "
            "(true только если автор явно подтверждает). "
            "Для to_plan — plan_title."
        )
        user = f"""{context}

Сообщение:
{message}

Есть фото: {has_photos}
"""
        parsed = await get_llm().complete_json(
            system=system,
            user=user,
            schema=_IntentOut,
            temperature=0.1,
            max_tokens=600,
        )
        intent = parsed.intent if parsed.intent in _VALID_INTENTS else "general"
        parsed.intent = intent
        if intent == "edit" and not parsed.draft_text:
            parsed.draft_text = message.strip()
        return parsed
    except ModelAsleepError:
        if len(message.strip()) >= 80:
            return _IntentOut(intent="edit", draft_text=message.strip())
        return _IntentOut(intent="general")
    except Exception:
        logger.exception("classify_intent failed")
        return _IntentOut(intent="general")


def _card(type_: str, title: str, body: str, data: dict | None = None, suggestion_id: int | None = None) -> ChatCard:
    return ChatCard(
        type=type_,
        title=title,
        body=body,
        data=data or {},
        suggestion_id=suggestion_id,
    )


async def _handle_today(session: AsyncSession) -> ChatOut:
    memory = MemoryStore(session)
    digest = await memory.latest_digest()
    plan = await memory.open_plan_items()
    cards: list[ChatCard] = []
    lines: list[str] = []
    if digest:
        lines.append(digest.body)
        for h in digest.highlights or []:
            text = h.get("text") if isinstance(h, dict) else str(h)
            if text:
                lines.append(f"· {text}")
    else:
        lines.append(f"Сводки нет. Сегодня {format_date_ru()}, {current_season()}.")

    idea_ids = (digest.idea_ids if digest else None) or []
    if idea_ids:
        result = await session.execute(select(Idea).where(Idea.id.in_(idea_ids)))
        for idea in result.scalars():
            cards.append(
                _card(
                    "idea",
                    idea.theme,
                    idea.description or idea.why_now or "",
                    {
                        "id": idea.id,
                        "format": idea.format,
                        "effort": idea.effort,
                        "why_now": idea.why_now,
                    },
                    idea.suggestion_id,
                )
            )
    elif await memory.count_posts() > 0:
        try:
            batch = await generate_ideas(session, count=2)
            for idea in batch.ideas:
                cards.append(
                    _card(
                        "idea",
                        idea.theme,
                        idea.description,
                        {
                            "id": idea.id,
                            "format": idea.format,
                            "effort": idea.effort,
                            "why_now": idea.why_now,
                        },
                        idea.suggestion_id,
                    )
                )
        except ModelAsleepError:
            lines.append("Идеи недоступны: текстовая модель не запущена.")

    if plan:
        lines.append("В плане:")
        for item in plan[:5]:
            lines.append(f"· {item.title} [{item.status}]")

    sids = [c.suggestion_id for c in cards if c.suggestion_id]
    return ChatOut(reply="\n".join(lines), cards=cards, suggestion_ids=sids, intent="today")


async def _handle_ideas(session: AsyncSession, count: int = 3) -> ChatOut:
    batch = await generate_ideas(session, count=count)
    cards = [
        _card(
            "idea",
            idea.theme,
            idea.description,
            {
                "id": idea.id,
                "format": idea.format,
                "effort": idea.effort,
                "why_now": idea.why_now,
                "personal_angle": idea.personal_angle,
                "visual": idea.visual,
            },
            idea.suggestion_id,
        )
        for idea in batch.ideas
    ]
    return ChatOut(
        reply=f"Идеи ({len(cards)}). Можно сказать «в план: …» или нажать действие под карточкой.",
        cards=cards,
        suggestion_ids=[c.suggestion_id for c in cards if c.suggestion_id],
        intent="ideas",
    )


async def _handle_analytics(session: AsyncSession) -> ChatOut:
    memory = MemoryStore(session)
    if await memory.count_posts() == 0:
        return ChatOut(reply="Архив пуст. Сначала импорт из VK.", intent="analytics")
    report = await analyze_audience(session)
    top = await memory.top_posts(90, 5)
    lines = [report.portrait or "Отчёт готов."]
    if report.what_works:
        lines.append("Что работает:")
        lines.extend(f"· {x}" for x in report.what_works[:5])
    if report.recommendations:
        lines.append("Делать чаще:")
        lines.extend(f"· {x}" for x in report.recommendations[:5])
    cards = [
        _card(
            "analytics",
            "Топ-посты",
            "\n".join(
                f"· {p.theme or (p.text or '')[:80]} (eng {p.engagement:.0f})" for p in top
            ),
            {"posts_count": await memory.count_posts()},
            report.suggestion_id,
        )
    ]
    return ChatOut(
        reply="\n".join(lines),
        cards=cards,
        suggestion_ids=[report.suggestion_id] if report.suggestion_id else [],
        intent="analytics",
    )


async def _handle_edit(session: AsyncSession, draft: str) -> ChatOut:
    if not draft.strip():
        return ChatOut(reply="Вставь черновик целиком — отредактирую.", intent="edit")
    result = await edit_draft(session, draft)
    cards = [
        _card(
            "edit",
            "Редактура",
            result.revised_text,
            {
                "revised_text": result.revised_text,
                "in_voice": result.in_voice,
                "voice_notes": result.voice_notes,
                "openings": result.alternative_openings,
                "edits": [e.model_dump() for e in result.edits],
            },
            result.suggestion_id,
        )
    ]
    voice = "В голосе" if result.in_voice else "Выбивается"
    return ChatOut(
        reply=f"{voice}. {result.voice_notes or ''}".strip(),
        cards=cards,
        suggestion_ids=[result.suggestion_id] if result.suggestion_id else [],
        intent="edit",
    )


async def _handle_photo(session: AsyncSession, paths: list[Path]) -> ChatOut:
    if not paths:
        return ChatOut(reply="Прикрепи фото к сообщению.", intent="photo")
    result = await analyze_photos(session, paths)
    body = (
        f"{result.verdict}\n\n"
        f"Подпись: {result.caption_direction or '—'}\n"
        + "\n".join(f"· {a}" for a in (result.advice or [])[:5])
    )
    cards = [
        _card(
            "photo",
            "Разбор фото",
            body,
            {
                "scores": result.scores.model_dump() if result.scores else {},
                "caption_direction": result.caption_direction,
                "verdict": result.verdict,
                "series_comparison": result.series_comparison,
                "best_in_series": result.best_in_series,
            },
            result.suggestion_id,
        )
    ]
    sids = [result.suggestion_id] if result.suggestion_id else []
    for adv in result.advice_suggestions or []:
        if adv.suggestion_id:
            sids.append(adv.suggestion_id)
            cards.append(_card("photo_advice", "Совет", adv.text, {}, adv.suggestion_id))
    return ChatOut(reply=result.verdict or "Разбор готов.", cards=cards, suggestion_ids=sids, intent="photo")


async def _handle_concierge(session: AsyncSession, message: str) -> ChatOut:
    # убрать служебные префиксы
    text = re.sub(
        r"^(ответь на|черновик ответа|это лс|личное сообщение)\s*:?\s*",
        "",
        message.strip(),
        flags=re.I,
    ).strip()
    reply = await draft_dm_reply(session, text)
    cards = [
        _card(
            "concierge",
            reply.category_label or reply.category,
            reply.draft_reply,
            {
                "category": reply.category,
                "related_post": reply.related_post,
                "draft_reply": reply.draft_reply,
            },
            reply.suggestion_id,
        )
    ]
    return ChatOut(
        reply=f"Тип: {reply.category_label}. Черновик ниже — отправка только вручную в VK.",
        cards=cards,
        suggestion_ids=[reply.suggestion_id] if reply.suggestion_id else [],
        intent="concierge",
    )


async def _handle_plan(session: AsyncSession) -> ChatOut:
    memory = MemoryStore(session)
    items = await memory.open_plan_items()
    all_result = await session.execute(select(PlanItem).order_by(desc(PlanItem.id)).limit(20))
    rows = list(all_result.scalars())
    if not rows:
        return ChatOut(reply="План пуст. Скажи «в план: тема» или попроси идеи.", intent="plan")
    hint = await memory.rhythm_hint()
    lines = [hint, ""]
    for item in rows[:12]:
        date = item.scheduled_date.date().isoformat() if item.scheduled_date else "без даты"
        lines.append(f"· [{item.status}] {item.title} — {date}")
    cards = []
    for item in items[:8]:
        date = item.scheduled_date.date().isoformat() if item.scheduled_date else None
        cards.append(
            _card(
                "plan_item",
                item.title,
                item.draft_text or "",
                {"id": item.id, "status": item.status, "scheduled_date": date},
            )
        )
    return ChatOut(reply="\n".join(lines), cards=cards, intent="plan")


async def _handle_to_plan(session: AsyncSession, title: str, draft: str = "") -> ChatOut:
    title = (title or "Без названия").strip()[:240]
    item = PlanItem(title=title, draft_text=draft.strip(), status="conceived")
    session.add(item)
    await MemoryStore(session).log("plan", f"В план из чата: {title}")
    await session.commit()
    await session.refresh(item)
    return ChatOut(
        reply=f"В плане: «{title}» (id {item.id}).",
        cards=[_card("plan_item", title, draft, {"id": item.id, "status": item.status})],
        intent="to_plan",
    )


async def _handle_seasonal(session: AsyncSession) -> ChatOut:
    result = await seasonal_reuse_suggestions(session)
    if not result.hits:
        return ChatOut(reply="В архиве пока нечего переиспользовать.", intent="seasonal")
    cards = [
        _card(
            "archive",
            hit.theme or f"пост #{hit.post_id}",
            hit.text_preview,
            {
                "post_id": hit.post_id,
                "engagement": hit.engagement,
                "why_relevant": hit.why_relevant,
            },
        )
        for hit in result.hits
    ]
    why = result.why.summary if result.why else "Сезонный архив"
    return ChatOut(reply=why, cards=cards, intent="seasonal")


async def _handle_inbox() -> ChatOut:
    if not is_configured():
        return ChatOut(reply="VK не настроен. Вставь текст ЛС вручную.", intent="inbox")
    try:
        raw = await fetch_inbox(15)
    except Exception as exc:
        return ChatOut(
            reply=getattr(exc, "user_message", None) or "Inbox недоступен. Вставь текст вручную.",
            intent="inbox",
        )
    items = raw.get("items") or []
    if not items:
        return ChatOut(reply="Входящих нет.", intent="inbox")
    cards = [
        _card(
            "inbox",
            f"peer {row.get('peer_id')}",
            row.get("preview") or "",
            {"peer_id": row.get("peer_id"), "date": row.get("date"), "unread": row.get("unread")},
        )
        for row in items
    ]
    return ChatOut(
        reply="Входящие. Напиши «ответь на: …» с текстом — подготовлю черновик.",
        cards=cards,
        intent="inbox",
    )


async def _handle_publish(
    session: AsyncSession,
    *,
    text: str,
    confirm: bool,
) -> ChatOut:
    if not confirm:
        return ChatOut(
            reply="Чтобы опубликовать, напиши явно: «опубликовать: текст» и слово «подтверждаю».",
            intent="publish",
        )
    body = text.strip()
    if not body:
        return ChatOut(reply="Нет текста для публикации.", intent="publish")
    try:
        result = await schedule_post(
            session,
            message=body,
            publish_date_unix=None,
            confirm=True,
        )
    except Exception as exc:
        msg = getattr(exc, "user_message", None) or str(exc)
        return ChatOut(reply=f"Не опубликовано: {msg}", intent="publish")
    warn = result.get("photos_warning")
    extra = f"\n{warn}" if warn else ""
    return ChatOut(
        reply=f"Опубликовано: {result.get('vk_post_id')}{extra}",
        cards=[_card("publish", "VK", body, result)],
        intent="publish",
    )


async def _handle_general(session: AsyncSession, message: str, history: list[dict[str, str]]) -> ChatOut:
    context = await build_agent_context(session)
    hist = "\n".join(f"{m['role']}: {m['content'][:400]}" for m in history[-8:])
    system = (
        f"{SYSTEM_ASSISTANT}\n"
        "Отвечай кратко и по делу. Если автор хочет действие "
        "(идеи, редактура, фото, ЛС, план, аналитика) — предложи конкретную формулировку."
    )
    user = f"""{context}

Недавний диалог:
{hist or '—'}

Сообщение автора:
{message}
"""
    try:
        text = await get_llm().complete(system=system, user=user, temperature=0.4, max_tokens=1200)
    except ModelAsleepError:
        return ChatOut(
            reply="Текстовая модель недоступна. Запусти brain на :8000 или используй команды: сегодня, идеи, аналитика, план.",
            intent="general",
        )
    return ChatOut(reply=text.strip() or "Пустой ответ модели.", intent="general")


async def handle_chat(
    session: AsyncSession,
    message: str,
    *,
    photo_paths: list[Path] | None = None,
) -> ChatOut:
    """Главная точка входа чата."""
    paths = photo_paths or []
    memory = MemoryStore(session)

    # сохранить user
    user_row = ChatMessage(role="user", content=message or ("[фото]" if paths else ""), cards=[], suggestion_ids=[])
    session.add(user_row)
    await session.flush()

    history_rows = await session.execute(
        select(ChatMessage).order_by(desc(ChatMessage.id)).limit(16)
    )
    history = [
        {"role": r.role, "content": r.content}
        for r in reversed(list(history_rows.scalars()))
        if r.id != user_row.id
    ]

    intent_info = await classify_intent(session, message, has_photos=bool(paths))
    intent = intent_info.intent

    try:
        if intent == "help":
            out = ChatOut(reply=_HELP, intent="help")
        elif intent == "today":
            out = await _handle_today(session)
        elif intent == "ideas":
            out = await _handle_ideas(session)
        elif intent == "analytics":
            out = await _handle_analytics(session)
        elif intent == "edit":
            out = await _handle_edit(session, intent_info.draft_text or message)
        elif intent == "photo":
            out = await _handle_photo(session, paths)
        elif intent == "concierge":
            out = await _handle_concierge(session, message)
        elif intent == "plan":
            out = await _handle_plan(session)
        elif intent == "to_plan":
            out = await _handle_to_plan(session, intent_info.plan_title or message)
        elif intent == "seasonal":
            out = await _handle_seasonal(session)
        elif intent == "inbox":
            out = await _handle_inbox()
        elif intent == "publish":
            out = await _handle_publish(
                session,
                text=intent_info.publish_text or message,
                confirm=intent_info.confirm_publish,
            )
        else:
            out = await _handle_general(session, message, history)
    except ModelAsleepError:
        out = ChatOut(
            reply="Модель недоступна. Проверь llama-server (:8000 / :8001).",
            intent=intent,
        )
    except Exception:
        logger.exception("chat handler failed intent=%s", intent)
        out = ChatOut(reply="Ошибка обработки. Попробуй ещё раз или переформулируй.", intent=intent)

    assistant = ChatMessage(
        role="assistant",
        content=out.reply,
        cards=[c.model_dump() for c in out.cards],
        suggestion_ids=out.suggestion_ids,
    )
    session.add(assistant)
    await memory.log("chat", f"Чат: {intent}", {"intent": intent})
    await session.commit()
    await session.refresh(assistant)
    out.cards = [ChatCard.model_validate(c) for c in (assistant.cards or [])]
    return out


async def list_chat_history(session: AsyncSession, limit: int = 80) -> list[ChatHistoryItem]:
    result = await session.execute(
        select(ChatMessage).order_by(desc(ChatMessage.id)).limit(limit)
    )
    rows = list(reversed(list(result.scalars())))
    return [
        ChatHistoryItem(
            id=row.id,
            role=row.role,  # type: ignore[arg-type]
            content=row.content or "",
            cards=row.cards or [],
            suggestion_ids=row.suggestion_ids or [],
            created_at=row.created_at.isoformat() if row.created_at else "",
        )
        for row in rows
    ]


async def clear_chat_history(session: AsyncSession) -> None:
    await session.execute(delete(ChatMessage))
    await MemoryStore(session).log("chat", "История чата очищена")
    await session.commit()


async def idea_to_plan_from_chat(session: AsyncSession, idea_id: int) -> ChatOut:
    idea = await session.get(Idea, idea_id)
    if idea is None:
        return ChatOut(reply="Идея не найдена.", intent="to_plan")
    item = PlanItem(idea_id=idea.id, title=idea.theme, draft_text="", status="conceived")
    session.add(item)
    idea.status = "planned"
    await MemoryStore(session).log("plan", f"В план из чата: {idea.theme}")
    await session.commit()
    return ChatOut(reply=f"«{idea.theme}» в плане.", intent="to_plan")

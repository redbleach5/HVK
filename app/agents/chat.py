"""Чат-роутер: сохраняет все возможности агентов в одном диалоге.

Структура (после рефактора):
- intent-classification в `app/agents/router.py`
- handlers регистрируются через `@register_handler(intent)`
- `_run_intent` — таблица маршрутов, не лестница if/elif
- `handle_chat` — точка входа для синхронных запросов
- `iter_chat_ndjson` — стрим
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.archive import seasonal_reuse_suggestions
from app.agents.audience import analyze_audience
from app.agents.base import (
    SYSTEM_ASSISTANT,
    ensure_why,
    save_agent_suggestion,
)
from app.agents.concierge import draft_dm_reply
from app.agents.editor import edit_draft
from app.agents.ideas import generate_ideas
from app.agents.photo import analyze_photos
from app.agents.router import (
    IntentDecision,
    classify_intent,
    classify_intent_heuristic,
    extract_concierge_text,
    register_handler,
)
from app.context.engine import ContextEngine, current_season, format_date_ru
from app.config import get_settings
from app.db.models import ChatMessage, Idea, PlanItem, Post
from app.llm.client import get_llm, strip_cot
from app.llm.exceptions import EmptyArchiveError, LlmResponseError, ModelAsleepError
from app.memory.citations import digest_cites_posts, digest_from_posts, post_citation
from app.memory.store import MemoryStore
from app.agents.chat_threads import ensure_thread, touch_thread
from app.agents.chat_limits import prepare_chat_message
from app.schemas.api import ChatCard, ChatHistoryItem, ChatOut
from app.schemas.common import WhyBlock
from app.vk.client import fetch_inbox, is_configured, schedule_post

logger = logging.getLogger(__name__)

_CHAT_EDITOR = (
    "Сначала ответь на её слова. "
    "Семью не суди. Заботу в её текстах замечай: конкретный жест из цитаты, не мораль. "
    "Не делай из боли тему для стены и не пиши пост добрее, чем она сама. "
    "Проницательность: номер поста и живая деталь из её текста, не «уютный контент». "
    "Доброта: если в архиве уже есть её тёплое слово — открой номер и её же деталь, без новой фразы за неё. "
    "Не предлагай формулировку, три строки и «кажется…», пока не попросит черновик или «поправь». "
    "Не выдумывай вещь, которой нет в цитате того поста, чей номер назвала. "
    "Если это работа со стеной, текстом или кадром — не урезай помощь: "
    "архив, самое лёгкое из уже сказанного, правка, разбор кадра — здесь, в этом ходе. "
    "«Можно не писать» — разрешение, не крышка. Не закрывай ворота, если она тянется к своему теплу. "
    "«Почему» из архива — когда это поддержка, не вместо того чтобы услышать. "
    "Не предлагай открыть другую вкладку. "
    "Не перечисляй, чего ты не сделаешь. "
    "В реплике — только живой текст."
)

_NO_ARCHIVE = (
    "Я пока не знаю твоих текстов — без них я просто угадаю, а не помогу. "
    "Вставь пару своих постов на этом экране — и я сразу подхвачу голос."
)

_HELP = (
    "Можно просто писать: что сегодня, идея, черновик, фото. "
    "Под карточками «учту» / «не соглашусь» — так я учусь. "
    "В VK сама ничего не выкладываю, пока явно не попросишь и не подтвердишь."
)


# --- Вспомогательные функции (без изменений по сути) ---

def _thought_card(thinking: str) -> ChatCard | None:
    text = (thinking or "").strip()
    if not text:
        return None
    return ChatCard(type="thinking", title="размышляю", body=text)


def _format_history(history: list[dict[str, str]]) -> str:
    """Свежие реплики целиком; старые — кратко. Прошлые мысли в промпт не кладём."""
    rows = history[-8:]
    if not rows:
        return ""
    older, recent = rows[:-3], rows[-3:]
    if len(rows) <= 3:
        older, recent = [], rows
    lines: list[str] = []
    if older:
        lines.append("Раньше в диалоге:")
        for item in older:
            role = "автор" if item.get("role") == "user" else "редакция"
            body = " ".join((item.get("content") or "").split())
            if len(body) > 280:
                body = body[:280].rstrip() + "…"
            if body:
                lines.append(f"— {role}: {body}")
        lines.append("Сейчас:")
    for item in recent:
        role = "автор" if item.get("role") == "user" else "редакция"
        body = (item.get("content") or "").strip()
        if len(body) > 1800:
            body = body[:1800].rstrip() + "…"
        if body:
            lines.append(f"{role}: {body}")
    return "\n".join(lines)


def plan_title_from_reply(reply: str, message: str) -> str:
    """Короткое название для плана — не готовый пост."""
    for raw in (reply or "").splitlines():
        line = raw.strip().lstrip("#*- ").strip()
        if line.startswith("**") and line.endswith("**") and len(line) > 4:
            line = line.strip("*").strip()
        if line[:1] in "«\"“'" or line.endswith(("»", '"', "”")):
            continue
        if 16 <= len(line) <= 110 and "?" not in line:
            low = line.lower()
            if low.startswith(("почему", "слушай", "итак", "в архиве", "потому")):
                continue
            return line[:240]
    clipped = " ".join((message or "").split())
    if not clipped:
        return "идея из диалога"
    return clipped[:80].rstrip()


def _general_chat_user(context: str, hist: str, message: str) -> str:
    """Промпт живого чата: стол, диалог, её слова. Без сценария настроения."""
    parts = [
        context,
        f"Недавний диалог:\n{hist or '—'}",
        f"Сообщение автора:\n{message}",
    ]
    return "\n\n".join(parts)


def _chat_system() -> str:
    return f"{SYSTEM_ASSISTANT}\n{_CHAT_EDITOR}"


def _web_card(hits: list[dict[str, str]]) -> ChatCard | None:
    titles = [h.get("title") or "" for h in hits if (h.get("title") or "").strip()]
    if not titles:
        return None
    urls = [h.get("url") or "" for h in hits if (h.get("url") or "").strip()]
    return _card("web", "из поиска", " · ".join(titles[:3]), {"urls": urls})


def looks_like_author_request(message: str) -> bool:
    """Вопрос к редакции — не «ты тут?» и не черновик поста."""
    raw = message or ""
    t = re.sub(r"\s+", " ", raw.strip().lower())
    if not t:
        return False
    hints = (
        "объясни", "подскажи", "что лучше", "что выложить", "что постить",
        "как думаешь", "помоги", "посоветуй", "не повторяться", "почему именно",
        "из архива", "мои тексты", "мой архив", "сообществ", "стен",
    )
    if any(h in t for h in hints):
        return True
    if "?" in raw and len(t) >= 24:
        return True
    return False


async def _ground_general(
    session: AsyncSession,
    *,
    message: str,
    reply: str,
    posts: list[Post],
) -> tuple[list[ChatCard], list[int]]:
    """Suggestion для учту. Карточка — только если она спросила про архив или стену."""
    labels = [post_citation(p) for p in posts[:4] if (p.text or "").strip()]
    why = ensure_why(
        WhyBlock(
            summary=(
                "Опираюсь на твои тексты" if labels else "Мало опоры в архиве — не выдумываю жизнь"
            ),
            related_posts=labels,
        ),
        "Опираюсь на архив",
    )
    title = plan_title_from_reply(reply, message)
    blocked, _matched = await MemoryStore(session).is_semantically_blocked(title)
    plan_title = "" if blocked else title
    suggestion = await save_agent_suggestion(
        session,
        kind="chat",
        title=title,
        payload={
            "post_ids": [p.id for p in posts[:6] if p.id],
            "message": (message or "")[:400],
        },
        why=why,
        log_action="chat",
        log_summary="Совет из диалога",
    )
    if not looks_like_author_request(message):
        return [], [suggestion.id]
    body = " · ".join(labels[:2]) if labels else ""
    card = _card(
        "why",
        "из твоих текстов",
        body,
        {"plan_title": plan_title, "post_ids": [p.id for p in posts[:6] if p.id]},
        suggestion.id,
    )
    return [card], [suggestion.id]


def _card(type_: str, title: str, body: str, data: dict | None = None, suggestion_id: int | None = None) -> ChatCard:
    return ChatCard(
        type=type_,
        title=title,
        body=body,
        data=data or {},
        suggestion_id=suggestion_id,
    )


# --- Handlers (регистрируются через декоратор) ---

@register_handler("help")
async def _handle_help(
    session: AsyncSession, message: str, paths: list[Path], history: list[dict[str, str]], decision: IntentDecision
) -> ChatOut:
    return ChatOut(reply=_HELP, intent="help")


@register_handler("today")
async def _handle_today(
    session: AsyncSession, message: str, paths: list[Path], history: list[dict[str, str]], decision: IntentDecision
) -> ChatOut:
    memory = MemoryStore(session)
    if await memory.count_author_posts() == 0:
        return ChatOut(reply=_NO_ARCHIVE, intent="today")
    digest = await memory.latest_digest()
    plan = await memory.open_plan_items()
    recent = await memory.recent_posts(4)
    cards: list[ChatCard] = []
    lines: list[str] = []
    archive_body, archive_highlights = digest_from_posts(recent)
    if digest and digest_cites_posts(digest.body, recent):
        lines.append(digest.body)
        for h in digest.highlights or []:
            text = h.get("text") if isinstance(h, dict) else str(h)
            if text:
                lines.append(f"· {text}")
    elif archive_body:
        lines.append(archive_body)
        for h in archive_highlights:
            lines.append(f"· {h['text']}")
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

    if plan:
        lines.append("В плане:")
        for item in plan[:5]:
            lines.append(f"· {item.title} [{item.status}]")

    sids = [c.suggestion_id for c in cards if c.suggestion_id]
    return ChatOut(reply="\n".join(lines), cards=cards, suggestion_ids=sids, intent="today")


@register_handler("ideas")
async def _handle_ideas(
    session: AsyncSession, message: str, paths: list[Path], history: list[dict[str, str]], decision: IntentDecision
) -> ChatOut:
    memory = MemoryStore(session)
    if await memory.count_author_posts() == 0:
        return ChatOut(reply=_NO_ARCHIVE, intent="ideas")
    batch = await generate_ideas(session, count=3)
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
    if not cards:
        return ChatOut(
            reply="Сейчас карточки не собрались. Напиши «идеи» ещё раз — я оперлась на архив, не на пустоту.",
            cards=[],
            intent="ideas",
        )
    return ChatOut(
        reply=f"Идеи ({len(cards)}). Можно сказать «в план: …» или нажать действие под карточкой.",
        cards=cards,
        suggestion_ids=[c.suggestion_id for c in cards if c.suggestion_id],
        intent="ideas",
    )


@register_handler("analytics")
async def _handle_analytics(
    session: AsyncSession, message: str, paths: list[Path], history: list[dict[str, str]], decision: IntentDecision
) -> ChatOut:
    memory = MemoryStore(session)
    if await memory.count_author_posts() == 0:
        return ChatOut(reply=_NO_ARCHIVE, intent="analytics")
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
            {"posts_count": await memory.count_author_posts()},
            report.suggestion_id,
        )
    ]
    return ChatOut(
        reply="\n".join(lines),
        cards=cards,
        suggestion_ids=[report.suggestion_id] if report.suggestion_id else [],
        intent="analytics",
    )


@register_handler("edit")
async def _handle_edit(
    session: AsyncSession, message: str, paths: list[Path], history: list[dict[str, str]], decision: IntentDecision
) -> ChatOut:
    draft = decision.draft_text or message
    if not draft.strip():
        return ChatOut(reply="Вставь черновик целиком — отредактирую.", intent="edit")
    if looks_like_author_request(draft):
        return await _handle_general(session, draft, history)
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


@register_handler("photo")
async def _handle_photo(
    session: AsyncSession, message: str, paths: list[Path], history: list[dict[str, str]], decision: IntentDecision
) -> ChatOut:
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


@register_handler("concierge")
async def _handle_concierge(
    session: AsyncSession, message: str, paths: list[Path], history: list[dict[str, str]], decision: IntentDecision
) -> ChatOut:
    text = extract_concierge_text(message)
    if not text:
        return ChatOut(
            reply="Вставь текст ЛС целиком — и я подготовлю черновик ответа.",
            intent="concierge",
        )
    if await MemoryStore(session).count_author_posts() == 0:
        return ChatOut(reply=_NO_ARCHIVE, intent="concierge")
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


@register_handler("plan")
async def _handle_plan(
    session: AsyncSession, message: str, paths: list[Path], history: list[dict[str, str]], decision: IntentDecision
) -> ChatOut:
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


@register_handler("to_plan")
async def _handle_to_plan(
    session: AsyncSession, message: str, paths: list[Path], history: list[dict[str, str]], decision: IntentDecision
) -> ChatOut:
    title = (decision.plan_title or message or "Без названия").strip()[:240]
    item = PlanItem(title=title, draft_text="", status="conceived")
    session.add(item)
    await MemoryStore(session).log("plan", f"В план из чата: {title}")
    await session.commit()
    await session.refresh(item)
    return ChatOut(
        reply=f"В плане: «{title}» (id {item.id}).",
        cards=[_card("plan_item", title, "", {"id": item.id, "status": item.status})],
        intent="to_plan",
    )


@register_handler("seasonal")
async def _handle_seasonal(
    session: AsyncSession, message: str, paths: list[Path], history: list[dict[str, str]], decision: IntentDecision
) -> ChatOut:
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


@register_handler("inbox")
async def _handle_inbox(
    session: AsyncSession, message: str, paths: list[Path], history: list[dict[str, str]], decision: IntentDecision
) -> ChatOut:
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


@register_handler("publish")
async def _handle_publish(
    session: AsyncSession, message: str, paths: list[Path], history: list[dict[str, str]], decision: IntentDecision
) -> ChatOut:
    if not is_configured():
        return ChatOut(
            reply="VK не подключён — публиковать некуда. Можно вставить текст поста вручную.",
            intent="publish",
        )
    if not decision.confirm_publish:
        return ChatOut(
            reply="Чтобы опубликовать, напиши явно: «опубликовать: текст» и слово «подтверждаю».",
            intent="publish",
        )
    body = (decision.publish_text or message).strip()
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


async def _iter_general_llm(
    *,
    system: str,
    user: str,
    hits: list[dict[str, str]],
):
    """Стрим мысли/текста; поиск — только если модель вызвала инструмент."""
    from app.llm.tools import WEB_TOOLS, run_web_tool

    llm = get_llm()
    user = llm.fit_chat_user(system, user)
    enabled = get_settings().web_search_enabled

    async def execute_tool(name: str, arguments: dict) -> str:
        text, found = await run_web_tool(name, arguments)
        hits.extend(found)
        return text

    async for kind, piece in llm.stream_thoughtful(
        system=system,
        user=user,
        temperature=0.4,
        label="chat",
        tools=WEB_TOOLS if enabled else None,
        execute_tool=execute_tool if enabled else None,
    ):
        yield kind, piece


async def _handle_general(session: AsyncSession, message: str, history: list[dict[str, str]]) -> ChatOut:
    if await MemoryStore(session).count_author_posts() == 0:
        return ChatOut(reply=_NO_ARCHIVE, intent="general")
    pack = await ContextEngine(session).pack(query=message)
    hist = _format_history(history)
    system = _chat_system()
    user = _general_chat_user(pack.text, hist, message)
    hits: list[dict[str, str]] = []
    thinking = ""
    text = ""
    try:
        async for kind, piece in _iter_general_llm(system=system, user=user, hits=hits):
            if kind == "thinking":
                thinking += piece
            elif kind == "text":
                text += piece
    except ModelAsleepError:
        return ChatOut(
            reply="Модель ещё просыпается — дай мне минутку и напиши ещё раз.",
            intent="general",
        )
    except LlmResponseError:
        text, thinking = "", ""
    text = strip_cot(text)
    cards = []
    thought = _thought_card(thinking)
    if thought:
        cards.append(thought)
    reply = text or "Пустой ответ — напиши ещё раз, пожалуйста."
    extra, sids = await _ground_general(
        session, message=message, reply=reply, posts=pack.posts
    )
    cards.extend(extra)
    found = _web_card(hits)
    if found:
        cards.append(found)
    return ChatOut(
        reply=reply,
        cards=cards,
        suggestion_ids=sids,
        intent="general",
    )


@register_handler("general")
async def _handle_general_wrapper(
    session: AsyncSession, message: str, paths: list[Path], history: list[dict[str, str]], decision: IntentDecision
) -> ChatOut:
    return await _handle_general(session, message, history)


async def stream_general_chat(
    session: AsyncSession,
    message: str,
    history: list[dict[str, str]],
) -> AsyncIterator[dict[str, Any]]:
    """Стрим хода мысли и реплики. Поиск — tool call модели, не эвристика."""
    if await MemoryStore(session).count_author_posts() == 0:
        yield {"t": "done", "reply": _NO_ARCHIVE, "cards": [], "intent": "general"}
        return
    pack = await ContextEngine(session).pack(query=message)
    hist = _format_history(history)
    system = _chat_system()
    user = _general_chat_user(pack.text, hist, message)
    hits: list[dict[str, str]] = []
    thinking_raw = ""
    text = ""
    n_think_ev = 0
    n_text_ev = 0
    n_search = 0
    try:
        async for kind, piece in _iter_general_llm(system=system, user=user, hits=hits):
            if kind == "thinking":
                thinking_raw += piece
                yield {"t": "thinking", "d": piece}
                n_think_ev += 1
            elif kind == "search":
                n_search += 1
                thinking_raw += f"\nсмотрю: {piece}\n"
                yield {"t": "search", "q": piece}
            elif kind == "text":
                text += piece
                yield {"t": "text", "d": piece}
                n_text_ev += 1
    except ModelAsleepError:
        logger.warning(
            "chat stream asleep msg_len=%s think_ev=%s text_ev=%s",
            len(message),
            n_think_ev,
            n_text_ev,
        )
        yield {
            "t": "done",
            "reply": "Модель ещё просыпается — дай мне минутку и напиши ещё раз.",
            "cards": [],
            "intent": "general",
        }
        return
    except LlmResponseError:
        yield {
            "t": "done",
            "reply": "Пустой ответ — напиши ещё раз, пожалуйста.",
            "cards": [],
            "intent": "general",
        }
        return
    text = strip_cot(text)
    cards: list[dict[str, Any]] = []
    thought = _thought_card(thinking_raw)
    if thought:
        cards.append(thought.model_dump())
    reply = text or "Пустой ответ — напиши ещё раз, пожалуйста."
    logger.info(
        "chat stream general think_ev=%s text_ev=%s search=%s think_raw=%s reply_len=%s hits=%s",
        n_think_ev,
        n_text_ev,
        n_search,
        len(thinking_raw),
        len(reply),
        len(hits),
    )
    extra, sids = await _ground_general(
        session, message=message, reply=reply, posts=pack.posts
    )
    cards.extend(c.model_dump() for c in extra)
    found = _web_card(hits)
    if found:
        cards.append(found.model_dump())
    yield {
        "t": "done",
        "reply": reply,
        "cards": cards,
        "intent": "general",
        "suggestion_ids": sids,
    }


# --- Главная точка входа ---

async def _run_intent(
    session: AsyncSession,
    message: str,
    paths: list[Path],
    history: list[dict[str, str]],
    decision: IntentDecision,
) -> ChatOut:
    """Таблица маршрутов: выбираем handler по интенту."""
    from app.agents.router import get_handler

    handler = get_handler(decision.intent)
    if handler is None:
        # Неизвестный интент — general
        handler = get_handler("general")
        if handler is None:
            return ChatOut(reply="Не получилось ответить. Напиши ещё раз.", intent="general")

    intent = decision.intent
    try:
        return await handler(session, message, paths, history, decision)
    except ModelAsleepError:
        return ChatOut(
            reply="Модель ещё просыпается — дай мне минутку и попробуй ещё раз.",
            intent=intent,
        )
    except EmptyArchiveError:
        return ChatOut(reply=_NO_ARCHIVE, intent=intent)
    except Exception:
        logger.exception("chat handler failed intent=%s", intent)
        return ChatOut(reply="Ошибка обработки. Попробуй ещё раз или переформулируй.", intent=intent)


async def handle_chat(
    session: AsyncSession,
    message: str,
    *,
    photo_paths: list[Path] | None = None,
    thread_id: int | None = None,
) -> ChatOut:
    """Главная точка входа чата."""
    paths = photo_paths or []
    message = prepare_chat_message(message or "")
    memory = MemoryStore(session)
    thread = await ensure_thread(session, thread_id)

    user_row = ChatMessage(
        thread_id=thread.id,
        role="user",
        content=message or ("[фото]" if paths else ""),
        cards=[],
        suggestion_ids=[],
    )
    session.add(user_row)
    await session.flush()
    await touch_thread(session, thread.id, message=message)

    history_rows = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread.id)
        .order_by(desc(ChatMessage.id))
        .limit(16)
    )
    history = [
        {"role": r.role, "content": r.content}
        for r in reversed(list(history_rows.scalars()))
        if r.id != user_row.id
    ]

    decision = await classify_intent(session, message, has_photos=bool(paths))
    out = await _run_intent(
        session, message, paths, history, decision
    )

    assistant = ChatMessage(
        thread_id=thread.id,
        role="assistant",
        content=out.reply,
        cards=[c.model_dump() for c in out.cards],
        suggestion_ids=out.suggestion_ids,
    )
    session.add(assistant)
    await touch_thread(session, thread.id)
    await memory.log("chat", f"Чат: {decision.intent} ({decision.source})", {"intent": decision.intent, "source": decision.source})
    await session.commit()
    await session.refresh(assistant)
    out.cards = [ChatCard.model_validate(c) for c in (assistant.cards or [])]
    return out


async def iter_chat_ndjson(
    session: AsyncSession,
    message: str,
    *,
    photo_paths: list[Path] | None = None,
    thread_id: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Стрим: ход мысли виден в диалоге; инструменты — одним куском."""
    paths = photo_paths or []
    message = prepare_chat_message(message or "")
    guessed = classify_intent_heuristic(message, has_photos=bool(paths))
    if paths or (guessed and guessed != "general"):
        out = await handle_chat(session, message, photo_paths=paths, thread_id=thread_id)
        yield {
            "t": "done",
            "reply": out.reply,
            "cards": [c.model_dump() for c in out.cards],
            "intent": out.intent,
            "suggestion_ids": out.suggestion_ids,
        }
        return

    thread = await ensure_thread(session, thread_id)
    memory = MemoryStore(session)
    user_row = ChatMessage(
        thread_id=thread.id,
        role="user",
        content=message or "",
        cards=[],
        suggestion_ids=[],
    )
    session.add(user_row)
    await session.commit()
    await touch_thread(session, thread.id, message=message)
    history_rows = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread.id)
        .order_by(desc(ChatMessage.id))
        .limit(16)
    )
    history = [
        {"role": r.role, "content": r.content}
        for r in reversed(list(history_rows.scalars()))
        if r.id != user_row.id
    ]
    done: dict[str, Any] | None = None
    t0 = time.perf_counter()
    logger.info(
        "chat stream start thread_id=%s msg_len=%s preview=%r",
        thread.id,
        len(message or ""),
        (message or "")[:80],
    )
    try:
        async for ev in stream_general_chat(session, message, history):
            yield ev
            if ev.get("t") == "done":
                done = ev
    except Exception:
        logger.exception(
            "stream general failed thread_id=%s dt=%.1fs",
            thread.id,
            time.perf_counter() - t0,
        )
        fail = "Не получилось ответить. Напиши ещё раз."
        yield {"t": "done", "reply": fail, "cards": [], "intent": "general"}
        done = {"reply": fail, "cards": [], "suggestion_ids": []}
    reply = (done or {}).get("reply") or "Не получилось ответить. Напиши ещё раз."
    raw_cards = (done or {}).get("cards") or []
    assistant = ChatMessage(
        thread_id=thread.id,
        role="assistant",
        content=reply,
        cards=raw_cards,
        suggestion_ids=(done or {}).get("suggestion_ids") or [],
    )
    session.add(assistant)
    await touch_thread(session, thread.id)
    await memory.log("chat", "Чат: general (stream)", {"intent": "general"})
    await session.commit()
    logger.info(
        "chat stream saved thread_id=%s reply_len=%s cards=%s dt=%.1fs",
        thread.id,
        len(reply),
        len(raw_cards),
        time.perf_counter() - t0,
    )


async def list_chat_history(
    session: AsyncSession,
    thread_id: int | None = None,
    limit: int = 80,
) -> tuple[int, list[ChatHistoryItem]]:
    thread = await ensure_thread(session, thread_id)
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.thread_id == thread.id)
        .order_by(desc(ChatMessage.id))
        .limit(limit)
    )
    rows = list(reversed(list(result.scalars())))
    items = [
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
    return thread.id, items


async def clear_chat_history(session: AsyncSession, thread_id: int | None = None) -> int:
    """Очищает сообщения диалога (legacy). Возвращает thread_id."""
    from app.agents.chat_threads import clear_thread_messages, ensure_thread

    thread = await ensure_thread(session, thread_id)
    await clear_thread_messages(session, thread.id)
    return thread.id


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

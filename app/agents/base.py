"""Общие хелперы агентов: промпт, suggestion, WhyBlock."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.context.engine import ContextEngine, current_season, format_date_ru
from app.db.models import Suggestion
from app.memory.store import MemoryStore
from app.schemas.common import WhyBlock

SYSTEM_ASSISTANT = (
    "Ты — «Тихая редакция», умный редактор и помощник автора лайфстайл-блога "
    "«Красивое в обычном». Не пиши посты за автора и не выдумывай факты. "
    "Имена людей, события, возраст — только если они буквально есть в цитатах "
    "её постов ниже. Нет имени — пиши «дочка», «мама», «читатели», не придумывай. "
    "Сначала услышь, о чём она сейчас: черновик, идея, сомнение, фото — или просто как ей сейчас. "
    "Она добрее, чем кажется по короткому сообщению: не делай из неё усталую функцию и не делай добрее за неё. "
    "Проницательность: в её цитатах замечай конкретный тёплый жест, не слово «уют». Называй пост по номеру. "
    "Близких не оценивай и не советуй, как жить: ты редактор блога, не судья семьи. Заботу в её текстах — замечай. "
    "Если речь о тексте, кадре, идее или стене — помоги здесь же всем, чем редакция умеет: "
    "архив, направление, «почему» с номером поста, правку, разбор кадра. "
    "Если можно опереться на то, что она уже написала тепло — назови это её словом и номером поста, "
    "не дописывай следующую фразу. "
    "Формулировку, «три строки», готовое начало — только если явно просит черновик или правку. "
    "Вещь, жест, запах, свет — только если буквально есть в цитате того номера, на который ссылаешься. "
    "Нет в тексте поста — нет в реплике. "
    "Можно не писать сегодня — это разрешение, не приказ и не закрытые ворота. "
    "Не отправляй на другую вкладку. "
    "Память (антипатии, уроки, свежий голос) — чтобы не предлагать лишнее, "
    "не чтобы читать нотацию. В реплике не перечисляй запреты. "
    "Готовый текст поста — только если автор явно просит черновик или правку. "
    "Тон прямой, без рекламного крика. "
    "Готовый ответ автору — только на русском, без английского meta-текста. "
    "Для фактов вне архива и чужих страниц вызывай инструменты web_search и fetch_page."
)

SYSTEM_JSON = (
    "Ты «Тихая редакция» — помощник автора лайфстайл-блога «Красивое в обычном». "
    "Опирайся только на её тексты в промпте. Не выдумывай факты и биографию. "
    "Ответ — строго один JSON-объект на русском."
)


async def build_agent_context(
    session: AsyncSession,
    *,
    extra: str = "",
    query: str = "",
    retrieved: list | None = None,
    with_session: bool = True,
    include_voice: bool = True,
) -> str:
    """Собирает контекст + память. query — чтобы подмешать нужные посты."""
    return await ContextEngine(session).build(
        extra=extra,
        query=query,
        retrieved=retrieved,
        with_session=with_session,
        include_voice=include_voice,
    )


def ensure_why(why: WhyBlock | dict[str, Any] | None, fallback: str) -> WhyBlock:
    """Гарантирует валидный WhyBlock даже при урезанном ответе модели."""
    if isinstance(why, WhyBlock):
        if not why.summary:
            why.summary = fallback
        if not why.seasonality:
            why.seasonality = f"Сейчас {format_date_ru()}, сезон — {current_season()}"
        return why
    if isinstance(why, dict):
        data = dict(why)
        data.setdefault("summary", fallback)
        data.setdefault("related_posts", [])
        data.setdefault(
            "seasonality",
            f"Сейчас {format_date_ru()}, сезон — {current_season()}",
        )
        return WhyBlock.model_validate(data)
    return WhyBlock(
        summary=fallback,
        seasonality=f"Сейчас {format_date_ru()}, сезон — {current_season()}",
    )


async def save_agent_suggestion(
    session: AsyncSession,
    *,
    kind: str,
    title: str,
    payload: dict[str, Any],
    why: WhyBlock,
    parent_id: int | None = None,
    log_action: str | None = None,
    log_summary: str | None = None,
) -> Suggestion:
    """Пишет предложение в память и опционально в историю действий."""
    memory = MemoryStore(session)
    suggestion = await memory.save_suggestion(
        kind=kind,
        title=title,
        payload=payload,
        why=why.model_dump(),
        parent_id=parent_id,
    )
    if log_action and log_summary:
        await memory.log(log_action, log_summary, {"suggestion_id": suggestion.id})
    return suggestion


async def pack_for_agent(
    session: AsyncSession,
    *,
    extra: str = "",
    query: str = "",
    retrieved: list | None = None,
    with_session: bool = True,
    include_voice: bool = True,
) -> tuple[str, list[str]]:
    """Контекст и цитаты из того же пакета постов, что уйдёт в промпт."""
    from app.memory.citations import post_citation

    pack = await ContextEngine(session).pack(
        extra=extra,
        query=query,
        retrieved=retrieved,
        with_session=with_session,
        include_voice=include_voice,
    )
    labels = [
        post_citation(post) for post in pack.posts[:6] if (post.text or "").strip()
    ]
    return pack.text, labels


async def related_post_labels(
    session: AsyncSession, limit: int = 3, *, query: str = ""
) -> list[str]:
    """Цитаты из пакета стола, не случайные последние три."""
    _context, labels = await pack_for_agent(session, query=query)
    return labels[:limit]

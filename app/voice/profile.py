"""Живой профиль голоса: строится из постов и обновляется после публикаций."""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.engine import ContextEngine
from app.db.models import Post, VoiceProfile
from app.llm.client import get_llm
from app.memory.store import MemoryStore

logger = logging.getLogger(__name__)

_WORD = re.compile(r"[а-яёa-z]+", re.IGNORECASE)

_STOP = {
    "и", "в", "на", "с", "по", "не", "что", "это", "как", "я", "мне", "мы",
    "у", "за", "от", "для", "но", "а", "то", "к", "из", "о", "же", "бы",
    "так", "все", "ещё", "еще", "уже", "или", "если", "когда", "просто",
}


def _stats_from_posts(posts: list[Post]) -> dict[str, Any]:
    """Простая статистика, независимая от LLM."""
    texts = [p.text for p in posts if p.text and p.text.strip()]
    if not texts:
        return {
            "avg_length_chars": 0,
            "avg_sentences": 0,
            "emoji_habits": "пока не видно",
            "frequent_words": [],
        }
    lengths = [len(t) for t in texts]
    sentences = [len(re.split(r"[.!?]+", t)) for t in texts]
    words: Counter[str] = Counter()
    hearts = sum(t.count("🤍") + t.count("✨") + t.count("🌿") for t in texts)
    for text in texts:
        for word in _WORD.findall(text.lower()):
            if word not in _STOP and len(word) > 2:
                words[word] += 1
    return {
        "avg_length_chars": int(sum(lengths) / len(lengths)),
        "avg_sentences": round(sum(sentences) / len(sentences), 1),
        "emoji_habits": "часто 🤍" if hearts > len(texts) / 3 else "редко, скорее 🤍 чем другие",
        "frequent_words": [w for w, _ in words.most_common(18)],
        "posts_used": len(texts),
    }


async def build_voice_profile(session: AsyncSession, *, source: str = "import") -> VoiceProfile:
    """Строит или обновляет профиль голоса по архиву постов."""
    result = await session.execute(
        select(Post).where(Post.text != "").order_by(desc(Post.published_at)).limit(40)
    )
    posts = list(result.scalars())
    stats = _stats_from_posts(posts)
    samples = "\n\n---\n\n".join((p.text or "")[:900] for p in posts[:12]) or "постов пока нет"

    profile_json: dict[str, Any]
    if posts:
        context = await ContextEngine(session).build()
        system = (
            "Ты бережно описываешь голос автора лайфстайл-блога. "
            "Не приукрашивай и не выдумывай биографию. "
            "Оттенки: recipes (рецепты), beauty (бьюти), home (дом), vlogs (тихие влоги)."
        )
        user = f"""{context}

Статистика черновиков:
{stats}

Образцы постов:
{samples}

Верни JSON:
{{
  "tone": "кратко",
  "address": "как обращается к читательнице",
  "avg_length_chars": {stats["avg_length_chars"]},
  "emoji_habits": "строка",
  "lexicon": ["слова"],
  "forbidden_vibes": ["чего в голосе нет"],
  "shades": {{
    "recipes": "как звучат рецепты",
    "beauty": "как звучат бьюти-ритуалы",
    "home": "как звучит дом",
    "vlogs": "как звучат влоги"
  }},
  "sample_phrases": ["2-4 характерные интонации, не цитаты целиком"]
}}
"""
        from pydantic import BaseModel, Field

        class VoiceJson(BaseModel):
            tone: str
            address: str
            avg_length_chars: int = 0
            emoji_habits: str = ""
            lexicon: list[str] = Field(default_factory=list)
            forbidden_vibes: list[str] = Field(default_factory=list)
            shades: dict[str, str] = Field(default_factory=dict)
            sample_phrases: list[str] = Field(default_factory=list)

        parsed = await get_llm().complete_json(system=system, user=user, schema=VoiceJson)
        profile_json = parsed.model_dump()
        profile_json["frequent_words"] = stats.get("frequent_words", [])
        profile_json["avg_length_chars"] = stats["avg_length_chars"]
    else:
        profile_json = {
            "tone": "мягкий, личный, без крика",
            "address": "на ты, как подруге",
            "avg_length_chars": 0,
            "emoji_habits": "редко, чаще 🤍",
            "lexicon": [],
            "forbidden_vibes": ["продающий", "кричащий", "инфоцыганский"],
            "shades": {
                "recipes": "спокойно, через ощущение, не как рецепт из журнала",
                "beauty": "как ритуал, не как разбор состава",
                "home": "находки и свет, без обзоров ради обзоров",
                "vlogs": "тихий кадр дня",
            },
            "sample_phrases": [],
            "frequent_words": [],
        }

    latest = await MemoryStore(session).latest_voice()
    version = (latest.version + 1) if latest else 1
    row = VoiceProfile(version=version, profile=profile_json, source=source)
    session.add(row)
    await MemoryStore(session).log("voice", f"Обновила голос, версия {version}")
    await session.commit()
    await session.refresh(row)
    logger.info("Профиль голоса v%s сохранён (%s)", version, source)
    return row


async def voice_is_ready(session: AsyncSession) -> bool:
    """Есть ли хотя бы одна версия профиля."""
    result = await session.execute(select(func.count(VoiceProfile.id)))
    return int(result.scalar_one()) > 0

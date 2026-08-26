# -*- coding: utf-8 -*-
"""Очистка мусора перед тестом Алины + проверка ответов с учётом сообщества.

1) Чистит чат, идеи, suggestions, digests, план, демо-посты, голос, chroma.
2) Временно кладёт 4 поста с комментариями читателей.
3) Прогоняет chat / ideas / analytics.
4) Снова чистит чат и сиды — Алине пустой стол (онбординг уже пройден).
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete

from app.agents.audience import analyze_audience
from app.agents.chat import handle_chat
from app.agents.ideas import generate_ideas
from app.db.models import (
    ActivityLog,
    Antipathy,
    AuthorProfile,
    ChatMessage,
    Digest,
    Idea,
    Lesson,
    PlanItem,
    Post,
    Preference,
    Rhythm,
    Suggestion,
    VoiceProfile,
)
from app.db.session import SessionLocal, init_db
from app.memory.chroma import get_chroma, upsert_post
from app.voice.profile import build_voice_profile

OUT = Path(r"C:\HVK\scripts\_tmp_alina_ready.json")

SEED_POSTS = [
    {
        "text": "Утром заварила чай в любимой чашке — пар, тишина, свет на столе. Никуда не спешу.",
        "likes": 42,
        "comments_count": 3,
        "views": 890,
        "engagement": 48.0,
        "theme": "утро",
        "comments": [
            {"text": "Как спокойно… хочется так же замедлиться"},
            {"text": "У меня тоже любимая чашка, спасибо что напомнили"},
            {"text": "Свет на столе — это отдельная любовь"},
        ],
    },
    {
        "text": "Нашла на блошином рынке льняную салфетку. Дома легла как будто всегда здесь жила.",
        "likes": 67,
        "comments_count": 4,
        "views": 1200,
        "engagement": 75.0,
        "theme": "дом",
        "comments": [
            {"text": "Где такие рынки у вас? Хочу тоже поискать"},
            {"text": "Лён дома — это про тепло, не про тренд"},
            {"text": "Вещи с историей всегда роднее новых"},
        ],
    },
    {
        "text": "Вечером простой рис с маслом и зеленью. Кажется, этого достаточно.",
        "likes": 55,
        "comments_count": 5,
        "views": 1100,
        "engagement": 62.0,
        "theme": "еда",
        "comments": [
            {"text": "Без рецептов — просто чувство. Это ваше"},
            {"text": "А можно чуть подробнее про зелень?"},
            {"text": "После сложных дней такое спасает"},
        ],
    },
    {
        "text": "Окно чуть запотело, за ним двор. Хочется сфотографировать не сюжет, а воздух.",
        "likes": 91,
        "comments_count": 6,
        "views": 2100,
        "engagement": 110.0,
        "theme": "свет",
        "comments": [
            {"text": "«Не сюжет, а воздух» — забираю себе в заметки"},
            {"text": "Ждём кадр, если решитесь показать"},
            {"text": "У нас тоже такое окно осенью"},
        ],
    },
]


async def wipe_session_junk(session, *, wipe_archive: bool) -> dict:
    counts: dict[str, int] = {}

    async def _wipe(model, name: str) -> None:
        r = await session.execute(delete(model))
        counts[name] = r.rowcount or 0

    await _wipe(ChatMessage, "chat_messages")
    await _wipe(ActivityLog, "activity_log")
    await _wipe(Digest, "digests")
    await _wipe(PlanItem, "plan_items")
    await _wipe(Idea, "ideas")
    await _wipe(Suggestion, "suggestions")
    await _wipe(Lesson, "lessons")
    await _wipe(Antipathy, "antipathies")
    await _wipe(Preference, "preferences")
    await _wipe(Rhythm, "rhythm")
    if wipe_archive:
        await _wipe(Post, "posts")
        await _wipe(VoiceProfile, "voice_profiles")
        try:
            col = get_chroma()
            ids = col.get().get("ids") or []
            if ids:
                col.delete(ids=ids)
            counts["chroma"] = len(ids)
        except Exception as exc:
            counts["chroma_error"] = str(exc)
    await session.commit()
    return counts


async def seed_community(session) -> list[int]:
    ids: list[int] = []
    base = datetime.now() - timedelta(days=12)
    for i, raw in enumerate(SEED_POSTS):
        post = Post(
            text=raw["text"],
            published_at=base + timedelta(days=i * 2),
            likes=raw["likes"],
            comments_count=raw["comments_count"],
            views=raw["views"],
            engagement=raw["engagement"],
            theme=raw["theme"],
            comments=raw["comments"],
            photo_urls=[],
        )
        session.add(post)
        await session.flush()
        try:
            upsert_post(
                post.id,
                post.text,
                {"theme": post.theme, "engagement": post.engagement},
            )
        except Exception as exc:
            # Chroma/эмбеддер иногда недоступен — для проверки сообщества хватает SQLite.
            print("chroma_skip", post.id, type(exc).__name__)
        ids.append(post.id)
    await session.commit()
    return ids


def _bad_reply(text: str) -> bool:
    low = (text or "").lower()
    markers = ("thinking process", "here's a thinking", "step 1:", "let's analyze", "<think>")
    return any(m in low for m in markers)


async def main() -> None:
    await init_db()
    report: dict = {"steps": []}

    async with SessionLocal() as session:
        profile = await session.get(AuthorProfile, 1)
        if profile is None:
            profile = AuthorProfile(
                id=1,
                blog_name="Красивое в обычном",
                about="Тихие находки дома, чай, свет, простые вещи.",
                onboarding_step=3,
                onboarding_done=True,
            )
            session.add(profile)
        else:
            profile.onboarding_done = True
            profile.onboarding_step = 3
            if not (profile.about or "").strip():
                profile.about = "Тихие находки дома, чай, свет, простые вещи."
        await session.commit()

        cleared = await wipe_session_junk(session, wipe_archive=True)
        report["steps"].append({"wipe_before": cleared})

        ids = await seed_community(session)
        report["steps"].append({"seed_post_ids": ids})

        voice = await build_voice_profile(session, source="seed")
        report["steps"].append({"voice_version": voice.version})

        chat_out = await handle_chat(
            session,
            "Привет. Что сейчас ближе моим читателям — утро с чаем или «воздух за окном»?",
        )
        report["chat"] = {
            "intent": chat_out.intent,
            "reply": (chat_out.reply or "")[:600],
            "cot_leak": _bad_reply(chat_out.reply or ""),
        }

        batch = await generate_ideas(session, count=2)
        ideas = list(getattr(batch, "ideas", None) or [])
        report["ideas"] = [
            {
                "theme": i.theme,
                "why_related": list(getattr(getattr(i, "why", None), "related_posts", None) or [])[:3],
                "why_summary": str(getattr(getattr(i, "why", None), "summary", "") or "")[:200],
            }
            for i in ideas
        ]

        audience = await analyze_audience(session)
        report["audience"] = {
            "portrait": (audience.portrait or "")[:400],
            "what_works": (audience.what_works or [])[:4],
            "frequent_questions": (audience.frequent_questions or [])[:4],
        }

        await wipe_session_junk(session, wipe_archive=True)
        report["steps"].append({"wipe_after": "archive+chat cleared for Alina"})
        report["handoff"] = (
            "Онбординг пройден. Архив пуст — Алине вставить 3–8 своих постов "
            "(лучше с живыми комментариями), чтобы сообщество попало в память."
        )

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT)
    if report.get("chat", {}).get("cot_leak"):
        print("FAIL cot_leak")
        sys.exit(1)
    if not (report.get("chat", {}).get("reply") or "").strip():
        print("FAIL empty chat")
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    asyncio.run(main())

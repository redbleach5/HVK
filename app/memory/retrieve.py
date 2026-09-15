"""Нужные посты к вопросу: векторный поиск + слова, не весь архив оптом."""

from __future__ import annotations

import asyncio
import logging
import math
import re

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Post
from app.memory.chroma import search_posts
from app.memory.store import _is_author_text

logger = logging.getLogger(__name__)

_WORD = re.compile(r"[а-яёa-z]{3,}", re.IGNORECASE)
_TAIL = ("а", "я", "о", "е", "ё", "у", "ю", "ы", "и", "й", "ь")

# Калибровка слоёв поиска (см. scripts/_probe_retrieval_weights.py и
# scripts/verify_retrieval_scoring.py). После e5 семантика точнее ключей:
# одиночное совпадение ключа не должно перебивать уверенный смысл.
_SEM_MULT = 7.0       # множитель семантического балла (2.2 - dist); калибровано в
                      # scripts/_probe_retrieval_weights.py: максимум самопоиска@3=15/15,
                      # e5-top3 в фьюжне 73%. e5 уверен — ключ становится подсказкой, а
                      # не конкурентом.
_SEM_FALLBACK = 2.5   # семантический балл, если distance не пришёл
_KEY_WEIGHT = 1.0     # вес за один совпавший ключ основы — подсказка для e5,
_ENGAGE_MULT = 200.0  # вклад вовлечённости в ключевой слой: лёгкий тай-брейк
                      # (макс +0.4), не игрок. При 40.0 посты с eng>100
                      # вытесняли уверенный e5-хит из top-3 самопоиска
                      # (см. scripts/_probe_selfsearch_fail.py)
_KEY_RARE_BOOST = 0.7  # редкий ключ — сильное свидетельство: «рец» из одного
                       # поста весит как несколько частых («каж», «пис»).
                       # Вклад ключа = 1 + BOOST * log2(N / (1 + df)).
_KEYWORD_SCAN = 400   # сколько постов просматриваем на ключи (не топ-120)


def _key(word: str) -> str:
    """Грубая основа слова: срезаем один хвостовой знак, берём три буквы.

    «чаю», «чаи» и «чай» дают «ча»; «дочку» и «дочь» — «доч»;
    «осенью» и «осенний» — «осе»; «соли» и «соль» — «сол».
    Точная морфология не нужна: ключ нужен, чтобы падежи
    не рвали словесный слой поиска.
    """
    word = word.lower().replace("ё", "е")
    if len(word) >= 3 and word.endswith(_TAIL):
        word = word[:-1]
    return word[:3]


_STOPWORDS = (
    "что", "чтобы", "как", "это", "этот", "для", "или", "если", "когда",
    "про", "чем", "еще", "уже", "есть", "был", "была", "было", "быть",
    "будет", "при", "под", "над", "тоже", "также", "потом", "который",
    "которая", "которые", "весь", "все", "мне", "тебе", "себе", "она",
    "они", "оно", "мой", "моя", "твой", "наш", "очень", "там", "тут",
    "вот", "где", "зачем", "почему", "так", "такой", "такая",
)
_STOP_KEYS = frozenset(_key(word) for word in _STOPWORDS)


def _keys(text: str) -> set[str]:
    """Множество основ текста без служебных слов.

    Служебные слова («что», «про»...) иначе дают мусорные ключи,
    которые забивают содержательный сигнал в словесном слое.
    """
    keys: set[str] = set()
    for word in _WORD.findall(text):
        key = _key(word)
        if key and key not in _STOP_KEYS:
            keys.add(key)
    return keys


async def posts_for_query(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 6,
) -> list[Post]:
    """Посты к этому сообщению: смысл + слова, рекламу выкидываем."""
    limit = max(1, min(limit, 12))
    scored: dict[int, tuple[float, Post]] = {}

    def add(post: Post | None, score: float) -> None:
        if post is None or not _is_author_text(post):
            return
        prev = scored.get(post.id)
        if prev is None:
            scored[post.id] = (score, post)
        else:
            # Слои складываются всегда: пост, у которого сильны и смысл, и
            # ключи, не должен терять семантику только потому, что ключевой
            # балл оказался выше (см. scripts/_probe_selfsearch_fail.py).
            scored[post.id] = (prev[0] + score * 0.35, prev[1])

    q = (query or "").strip()
    if q:
        try:
            raw = await asyncio.to_thread(search_posts, q, limit + 8)
        except Exception:
            logger.exception("Поиск по архиву не удался — иду по словам")
            raw = []
        for hit in raw:
            post = await session.get(Post, int(hit.get("post_id") or 0))
            dist = hit.get("distance")
            if dist is None:
                semantic = _SEM_FALLBACK
            else:
                semantic = max(0.0, 2.2 - float(dist)) * _SEM_MULT
            add(post, semantic)

    query_keys = _keys(q)
    keyword_posts, key_weights = await _keyword_posts(
        session, q, limit=max(limit * 4, 16)
    )
    for post in keyword_posts:
        if query_keys:
            shared = query_keys & _keys(post.text or "")
            overlap_score = sum(key_weights.get(k, _KEY_WEIGHT) for k in shared)
        else:
            overlap_score = _KEY_WEIGHT
        add(
            post,
            overlap_score + min(float(post.engagement or 0), 80.0) / _ENGAGE_MULT,
        )

    return [post for _, post in sorted(scored.values(), key=lambda item: -item[0])[:limit]]


async def _keyword_posts(
    session: AsyncSession, query: str, *, limit: int
) -> tuple[list[Post], dict[str, float]]:
    """Посты по словам + вес каждого совпавшего ключа (IDF-lite).

    Редкий ключ («рец» — в одном посте) — сильное свидетельство, частый
    («каж») — слабая подсказка. Вес = 1 + BOOST * log2(N / (1 + df)).
    """
    words = _WORD.findall((query or "").lower())
    result = await session.execute(
        select(Post).order_by(desc(Post.engagement), desc(Post.id)).limit(_KEYWORD_SCAN)
    )
    rows = [p for p in result.scalars() if _is_author_text(p)]
    if not words:
        return rows[:limit], {}
    query_keys = _keys(query or "")
    if not query_keys:
        # Слова есть, но все ключи служебные — не оставляем автора без
        # ответа: отдаём популярное, как и при вовсе пустом запросе.
        return rows[:limit], {}
    post_keys = [(post, _keys(post.text or "")) for post in rows]
    weights = {}
    for key in query_keys:
        df = sum(1 for _, pk in post_keys if key in pk)
        if df:
            weights[key] = _KEY_WEIGHT + _KEY_RARE_BOOST * math.log2(
                len(rows) / (1 + df)
            )
    scored: list[tuple[float, float, Post]] = []
    for post, pk in post_keys:
        score = sum(weights.get(k, 0.0) for k in query_keys & pk)
        if score:
            scored.append((score, float(post.engagement or 0), post))
    scored.sort(key=lambda item: (-item[0], -item[1]))
    return [item[2] for item in scored[:limit]], weights


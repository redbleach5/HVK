# -*- coding: utf-8 -*-
"""Гейт: память, которую выучила редакция, видна автору и её можно поправить.

Запуск: C:\\HVK\\.venv\\Scripts\\python.exe scripts\\verify_memory_visible.py

Без LLM. База — временная, своя не трогается.

Зачем. Обратная связь работала только в одну сторону: автор отвечал
«учту» или «не соглашусь», и выученное уходило в промпт навсегда.
Посмотреть, чему она научилась, было нельзя — и исправить тоже. А
антипатия это обещание «больше не предлагать»: если автор отклонил
правку формулировки, а редакция решила, что нелюбима сама тема, то
тема молча исчезает на весь срок. Убрать это было нечем.

Провал = автор снова не видит, что о нём выучено, либо запрет нельзя
снять. Тогда ошибка в памяти живёт до истечения срока, а автор даже
не знает, что она есть.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="hvk-mem-"))
os.environ["DATABASE_PATH"] = str(_TMP / "app.db")
os.environ["CHROMA_ENABLED"] = "0"

import asyncio  # noqa: E402

from sqlalchemy import select  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _utcnow():
    """Наивный UTC — тот же, что ждёт store._active_antipathies."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed():
    """Кладёт по одной записи каждого вида. Своя временная база, чистится."""
    from sqlalchemy import delete

    from app.db.models import Antipathy, Lesson, Preference

    async def go() -> None:
        from app.db.session import SessionLocal, init_db

        await init_db()
        # Чистим прошлый заход: каждый тест видит ровно свои четыре записи.
        async with SessionLocal() as s:
            await s.execute(delete(Antipathy))
            await s.execute(delete(Lesson))
            await s.execute(delete(Preference))
            await s.commit()

        async with SessionLocal() as s:
            s.add(Preference(kind="themes", key="осенний свет", value="зашло", weight=1.2))
            s.add(
                Lesson(
                    title="Откликнулось: тихий вечер",
                    outcome="success",
                    why="вовлечённость выросла",
                )
            )
            s.add(
                Antipathy(
                    topic="снимки с чужими людьми",
                    reason="автор не любит",
                    expires_at=_utcnow() + timedelta(days=40),
                )
            )
            s.add(
                Antipathy(
                    topic="давно ушедшая тема",
                    reason="срок вышел",
                    expires_at=_utcnow() - timedelta(days=1),
                )
            )
            await s.commit()

    _run(go())


def test_memory_lists_what_was_learned() -> None:
    """Видны все три вида: что зашло, что нет, что запрещено."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    data = client.get("/memory").json()

    assert data["total"] == 4, data["total"]
    assert [p["key"] for p in data["preferences"]] == ["осенний свет"]
    assert [lesson["outcome"] for lesson in data["lessons"]] == ["success"]

    topics = {a["topic"]: a for a in data["antipathies"]}
    assert "снимки с чужими людьми" in topics
    assert "давно ушедшая тема" in topics, "истёкший запрет должен быть виден, но помечен"
    # Живой и истёкший не должны выглядеть одинаково
    assert topics["снимки с чужими людьми"]["expired"] is False
    assert topics["давно ушедшая тема"]["expired"] is True
    # Причина видна: автор должен понимать, почему это запрещено
    assert topics["снимки с чужими людьми"]["why"] == "автор не любит"
    client.close()


def test_antipathy_can_be_forgotten() -> None:
    """Главное: неверно понятый запрет автор снимает сам."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    before = client.get("/memory").json()
    target = next(
        a for a in before["antipathies"] if a["topic"] == "снимки с чужими людьми"
    )

    removed = client.delete(f"/memory/antipathies/{target['id']}")
    assert removed.status_code == 200, removed.text
    assert removed.json()["ok"] is True

    after = client.get("/memory").json()
    assert target["id"] not in {a["id"] for a in after["antipathies"]}
    assert "снимки с чужими людьми" not in {a["topic"] for a in after["antipathies"]}
    # Остальное не тронуто
    assert len(after["preferences"]) == 1
    assert len(after["lessons"]) == 1
    client.close()


def test_deleted_antipathy_leaves_the_prompt() -> None:
    """Снятый запрет обязан исчезнуть из того, что уходит в промпт.

    Иначе автор видит «забыто», а модель всё равно его читает.
    """
    from fastapi.testclient import TestClient

    from app.db.models import Antipathy
    from app.db.session import SessionLocal
    from app.main import create_app
    from app.memory.store import MemoryStore

    async def find_topic() -> int | None:
        async with SessionLocal() as s:
            row = (
                await s.execute(
                    select(Antipathy).where(Antipathy.topic == "снимки с чужими людьми")
                )
            ).scalar_one_or_none()
            return row.id if row else None

    async def in_prompt(topic: str) -> bool:
        async with SessionLocal() as s:
            return topic in await MemoryStore(s).antipathy_topics()

    aid = _run(find_topic())
    assert aid is not None, "антипатия должна быть в базе"

    # До снятия запрет обязан быть в промпте — иначе проверка бессмысленна
    assert _run(in_prompt("снимки с чужими людьми")) is True, "запрет должен быть в промпте"

    client = TestClient(create_app())
    client.delete(f"/memory/antipathies/{aid}")
    client.close()

    assert _run(in_prompt("снимки с чужими людьми")) is False, "снятый запрет всё ещё в промпте"
    assert _run(in_prompt("давно ушедшая тема")) is False, "истёкший не должен попадать в промпт"


def test_memory_route_exists() -> None:
    from app.main import create_app

    paths = create_app().openapi()["paths"]
    assert "get" in paths.get("/memory", {})
    assert "delete" in paths.get("/memory/antipathies/{antipathy_id}", {})


def main() -> int:
    print("=== память видна автору ===")
    # Каждая проверка начинается со своей базы: иначе тесты зависят
    # от порядка — снятая антипатия исчезла бы из-под следующего.
    failures = 0
    for name, fn in (
        ("выученное видно", test_memory_lists_what_was_learned),
        ("запрет можно снять", test_antipathy_can_be_forgotten),
        ("снятое уходит из промпта", test_deleted_antipathy_leaves_the_prompt),
        ("маршруты на месте", test_memory_route_exists),
    ):
        try:
            _seed()
            fn()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ПРОВАЛ {name}: {type(exc).__name__}: {str(exc)[:200]}")
            continue
        print(f"ок    {name}")

    print()
    if failures:
        return 1
    print("ОК: автор видит память и может снять неверный запрет")
    return 0


if __name__ == "__main__":
    sys.exit(main())

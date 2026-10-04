# -*- coding: utf-8 -*-
"""Гейт: /memory не падает на пустой памяти и на кривых данных.

Запуск: C:\\HVK\\.venv\\Scripts\\python.exe scripts\\verify_memory_robust.py

Без LLM. Своя временная база.

Зачем. /memory открывает страницу «что она запомнила», а страницу автор
открывает и на первом запуске — когда выучено ещё ничего. Пустой
список это нормальное состояние, а не ошибка. И наоборот: один испорченный
урок не должен ронять всю страницу, потому что память нужна для того,
чтобы автор мог её поправить.

Провал = на пустой базе ручка отдаёт не список, а ошибку — тогда автор
не сможет открыть страницу памяти именно тогда, когда редакция ещё
ничего не знает о нём.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="hvk-memrobust-"))
os.environ["DATABASE_PATH"] = str(_TMP / "app.db")
os.environ["CHROMA_ENABLED"] = "0"

import asyncio  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app())


def _init() -> None:
    from app.db.session import init_db

    _run(init_db())


def test_empty_memory_returns_empty_lists() -> None:
    """Первый запуск: выучено ничего, страница должна открыться."""
    _init()
    client = _client()
    data = client.get("/memory").json()

    assert data["preferences"] == [], data
    assert data["antipathies"] == [], data
    assert data["lessons"] == [], data
    assert data["total"] == 0, data
    client.close()


def test_lessons_zero_is_allowed() -> None:
    """lessons=0 — автор просит без уроков, это не ошибка."""
    client = _client()
    data = client.get("/memory", params={"lessons": 0}).json()
    assert data["lessons"] == []
    client.close()


def test_memory_works_without_archive() -> None:
    """Память не зависит от того, импортирован ли архив.

    На первом запуске архива ещё нет, а страница памяти уже должна
    открываться — иначе автор не увидит, что редакция пока ничего
    о нём не знает.
    """
    client = _client()
    assert client.get("/memory").status_code == 200
    client.close()


def test_antipathy_without_expiry_never_expires() -> None:
    """Антипатия без срока должна жить и показываться как живая.

    Иначе автор увидит «живое» как истёкшее и решит, что можно убрать.
    """
    from app.db.models import Antipathy
    from app.db.session import SessionLocal

    async def seed() -> None:
        async with SessionLocal() as s:
            s.add(Antipathy(topic="вечная тема", reason="не знаю"))
            await s.commit()

    _run(seed())
    client = _client()
    data = client.get("/memory").json()
    row = next(a for a in data["antipathies"] if a["topic"] == "вечная тема")
    assert row["expired"] is False, row
    assert row["expires_at"] is None, row
    client.close()


def test_delete_missing_antipathy_is_404() -> None:
    """Снять несуществующее — понятный отказ, а не 500."""
    client = _client()
    response = client.delete("/memory/antipathies/999999")
    assert response.status_code == 404, response.status_code
    client.close()


def test_delete_twice_second_is_404() -> None:
    """Повторное нажатие «забыть» не должно ронять страницу."""
    from app.db.models import Antipathy
    from app.db.session import SessionLocal

    async def seed() -> int:
        async with SessionLocal() as s:
            row = Antipathy(topic="разовая", reason="x")
            s.add(row)
            await s.commit()
            return row.id

    aid = _run(seed())
    client = _client()
    assert client.delete(f"/memory/antipathies/{aid}").status_code == 200
    second = client.delete(f"/memory/antipathies/{aid}")
    assert second.status_code == 404, second.status_code
    client.close()


def test_bad_limit_is_rejected() -> None:
    """lessons=9999 — не молча отдавать всё, а отвечать понятно."""
    client = _client()
    assert client.get("/memory", params={"lessons": 9999}).status_code == 422
    client.close()


def main() -> int:
    print("=== память не ломается на краях ===")
    failures = 0
    for name, fn in (
        ("пустая память — пустые списки", test_empty_memory_returns_empty_lists),
        ("lessons=0 допустим", test_lessons_zero_is_allowed),
        ("работает без архива", test_memory_works_without_archive),
        ("антипатия без срока жива", test_antipathy_without_expiry_never_expires),
        ("снять отсутствующее — 404", test_delete_missing_antipathy_is_404),
        ("повторное снятие — 404", test_delete_twice_second_is_404),
        ("неверный лимит — 422", test_bad_limit_is_rejected),
    ):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ПРОВАЛ {name}: {type(exc).__name__}: {str(exc)[:200]}")
            continue
        print(f"ок    {name}")

    print()
    if failures:
        return 1
    print("ОК: страница памяти открывается всегда, даже когда пусто")
    return 0


if __name__ == "__main__":
    sys.exit(main())

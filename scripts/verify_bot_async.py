# -*- coding: utf-8 -*-
"""Гейт: бот не встаёт колом, пока модель думает.

Запуск: C:\\HVK\\.venv\\Scripts\\python.exe scripts\\verify_bot_async.py

Без LLM и без сети.

Живой риск: бот ходил в локальный API синхронным ``httpx.Client``
(таймаут 1200 секунд) прямо из async-хендлеров aiogram. Синхронный вызов
в async-коде блокирует event loop всего бота: одна холодная модель
зависала не только свою команду, но и все остальные — включая /today.
Плюс на каждый запрос открывалось новое соединение.

Провал = в bot/main.py снова появился sync httpx или хендлер вызывает
_get/_post без await. Тогда телефон перестаёт отвечать, пока идёт
любой один запрос.
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SOURCE = ROOT / "bot" / "main.py"


def test_client_is_async() -> None:
    """Клиент обязан быть httpx.AsyncClient."""
    from bot.main import _api

    client = _api()
    assert isinstance(client, httpx_async_client_type()), type(client)
    # второй вызов возвращает тот же клиент, а не новый
    assert _api() is client, "соединение должно переиспользоваться"


def httpx_async_client_type():
    import httpx

    return httpx.AsyncClient


def test_helpers_are_coroutines() -> None:
    from bot.main import _get, _post

    assert inspect.iscoroutinefunction(_get), "_get должен быть async"
    assert inspect.iscoroutinefunction(_post), "_post должен быть async"
    assert inspect.iscoroutinefunction(bot_close()), "_close_api должен быть async"


def bot_close():
    from bot.main import _close_api

    return _close_api


def test_no_sync_client_in_source() -> None:
    """Синхронный httpx.Client в боте — прямой путь к зависанию."""
    src = SOURCE.read_text(encoding="utf-8")
    code = "\n".join(
        line for line in src.splitlines() if not line.strip().startswith("#")
    )
    if "httpx.Client(" in code and "httpx.AsyncClient(" not in code.split("httpx.Client(")[0][-40:]:
        raise AssertionError("вернулся синхронный httpx.Client")
    if "def _api() -> httpx.Client" in code:
        raise AssertionError("_api снова возвращает sync-клиент")


def test_handlers_await_api() -> None:
    """Каждый вызов _get/_post обязан быть под await.

    Хендлеры вложены в create_dispatcher, поэтому у вызова ищем
    БЛИЖАЙШУЮ объемлющую функцию, а не любую: иначе всё попадёт
    в sync-обёртку create_dispatcher.
    """
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    parent: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[id(child)] = node

    def enclosing(node: ast.AST):
        cur = parent.get(id(node))
        while cur is not None:
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cur
            cur = parent.get(id(cur))
        return None

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Name) and fn.id in ("_get", "_post")):
            continue
        owner = enclosing(node)
        if owner is None:
            offenders.append(f":{node.lineno} — {fn.id}() вне функции")
        elif not isinstance(owner, ast.AsyncFunctionDef):
            offenders.append(f"{owner.name}:{node.lineno} — {fn.id}() в sync-функции")

    assert not offenders, "вызовы без await: " + ", ".join(offenders)


def test_event_loop_stays_free_while_api_is_slow() -> None:
    """Главная проверка: тик луп продолжается, пока «модель думает»."""
    import asyncio

    async def scenario() -> bool:
        from bot import main as bot_main

        # Подменяем транспорт: реальный API не нужен и не должен трогаться.
        async def slow_get(path: str, **params):
            await asyncio.sleep(0.2)
            return {"digest": "тихо"}

        bot_main._get = slow_get
        ticks = {"n": 0}

        async def ticker():
            # Тикает, пока бот «ждёт модель»
            for _ in range(10):
                await asyncio.sleep(0.01)
                ticks["n"] += 1

        async def user_command():
            return await bot_main._get("/today")

        await asyncio.gather(user_command(), ticker())
        return ticks["n"] >= 5

    assert asyncio.run(scenario()), (
        "event loop встал во время ожидания ответа API — бот зависнет"
    )


def main() -> int:
    print("=== бот не блокирует event loop ===")
    failures = 0
    for name, fn in (
        ("клиент асинхронный и переиспользуемый", test_client_is_async),
        ("_get/_post — корутины", test_helpers_are_coroutines),
        ("нет sync httpx в исходнике", test_no_sync_client_in_source),
        ("хендлеры ждут через await", test_handlers_await_api),
        ("луп живёт во время медленного ответа", test_event_loop_stays_free_while_api_is_slow),
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
    print("ОК: бот отвечает на все команды, пока модель думает")
    return 0


if __name__ == "__main__":
    sys.exit(main())

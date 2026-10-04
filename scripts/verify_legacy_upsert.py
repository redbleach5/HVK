# -*- coding: utf-8 -*-
"""Гейт: запасной режим эмбеддера не падает и не режет посты.

Запуск: C:\\HVK\\.venv\\Scripts\\python.exe scripts\\verify_legacy_upsert.py

Без LLM. Свой каталог Chroma в темпе, чужая коллекция не трогается.

Живой баг: последняя строка upsert_post содержала documents=[doc], а
переменной doc не было нигде в файле. Путь достигался только когда
активный режим не nomic и не e5, то есть на том самом запасном пути
(Ollama без модели -> e5 нет -> legacy MiniLM), который объявлен
рабочим. Симптом: NameError на каждом импорте поста, импорт молча
падает целиком.

Вторая половина той же строки важнее первого: класть parts[0] нельзя,
длинный пост потерял бы всё после первого куска и тихо выпал бы из
поиска. Legacy-коллекция хранит посты целиком.

Провал = запасной режим падает, или длинный пост попадает в индекс
обрезанным. Тогда автор либо не может импортировать архив, либо не
находит то, что уже загрузил.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="hvk-legacy-"))
os.environ["CHROMA_PATH"] = str(_TMP / "chroma")
os.environ["CHROMA_ENABLED"] = "1"

import app.memory.chroma as chroma  # noqa: E402

LONG_TEXT = (
    "Утро. Свет из окна падает на чашку, и это тот самый час, ради "
    "которого встаёшь раньше будильника. "
) * 40  # заведомо длиннее одного куска


def _force_legacy() -> None:
    """Переключает модуль на legacy-режим: векторного слоя нет."""
    chroma._semantic_mode = lambda: None  # noqa: SLF001
    chroma._collections.clear()


def test_short_post_imports() -> None:
    """Короткий пост: без NameError, лежит под своим id."""
    _force_legacy()
    chroma.upsert_post(101, "Осенний свет в окне", {"theme": "осень"})

    collection = chroma.get_chroma()
    got = collection.get(ids=["101"], include=["documents", "metadatas"])
    docs = got.get("documents") or []
    assert docs, "пост не лёг в индекс"
    assert "Осенний свет" in docs[0]


def test_long_post_keeps_whole_text() -> None:
    """Длинный пост ложится целиком, а не первым куском.

    Обрезка здесь выглядит как «всё работает», но пост выпадает из
    поиска по своему же содержанию.
    """
    _force_legacy()
    chroma.upsert_post(102, LONG_TEXT, {"theme": "длинный"})

    collection = chroma.get_chroma()
    got = collection.get(ids=["102"], include=["documents"])
    docs = got.get("documents") or []
    assert docs, "длинный пост не лёг в индекс"
    stored = docs[0]
    assert len(stored) > 1000, f"пост обрезан до {len(stored)} символов"
    assert stored.strip() == LONG_TEXT.strip()[: len(stored)].strip() or stored.strip()[
        :80
    ] == LONG_TEXT.strip()[:80], "начало поста не совпадает"
    # хвост тоже на месте
    assert stored.strip()[-80:].strip() == LONG_TEXT.strip()[-80:].strip(), "хвост потерян"


def test_upsert_twice_replaces_not_duplicates() -> None:
    """Повторный импорт того же поста не плодит записи."""
    _force_legacy()
    chroma.upsert_post(103, "Первый вариант", {"theme": "x"})
    chroma.upsert_post(103, "Второй вариант", {"theme": "x"})

    collection = chroma.get_chroma()
    assert collection.get(ids=["103"], include=["documents"]).get("documents") == [
        "Второй вариант"
    ]


def test_metadata_kept() -> None:
    """Метаданные нужны поиску: тема и id поста."""
    _force_legacy()
    chroma.upsert_post(104, "Кадр с кофе", {"theme": "кофе", "engagement": 12.0})

    got = chroma.get_chroma().get(ids=["104"], include=["metadatas"])
    meta = (got.get("metadatas") or [{}])[0]
    assert meta.get("post_id") == 104, meta
    assert meta.get("theme") == "кофе", meta


def test_no_undefined_names_left() -> None:
    """Страховка от того же класса ошибки: нет имён вне области видимости.

    Имена уровня модуля (импорты, константы) считаем объявленными:
    без этого проверка ругается на любой импорт из верхнего модуля.
    """
    import ast

    src = (ROOT / "app" / "memory" / "chroma.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    module_names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                module_names.add(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            module_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    module_names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            module_names.add(node.target.id)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        assigned = set(module_names)
        used: list[tuple[str, int]] = []
        for inner in ast.walk(node):
            if isinstance(inner, ast.Name):
                if isinstance(inner.ctx, ast.Store):
                    assigned.add(inner.id)
                else:
                    used.append((inner.id, inner.lineno))
            elif isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                assigned.add(inner.name)
            elif isinstance(inner, ast.arg):
                assigned.add(inner.arg)
            elif isinstance(inner, ast.ExceptHandler) and inner.name:
                assigned.add(inner.name)
            elif isinstance(inner, (ast.Import, ast.ImportFrom)):
                for alias in inner.names:
                    assigned.add((alias.asname or alias.name).split(".")[0])

        builtins = set(dir(__builtins__)) | {"self", "cls"}
        for name, lineno in used:
            if name not in assigned and name not in builtins:
                raise AssertionError(f"{node.name}:{lineno} — имя {name!r} не определено")


def main() -> int:
    print("=== запасной режим эмбеддера ===")
    failures = 0
    for name, fn in (
        ("короткий пост ложится", test_short_post_imports),
        ("длинный пост целиком", test_long_post_keeps_whole_text),
        ("повторный импорт заменяет", test_upsert_twice_replaces_not_duplicates),
        ("метаданные на месте", test_metadata_kept),
        ("нет неопределённых имён", test_no_undefined_names_left),
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
    print("ОК: запасной режим импортирует посты целиком и не падает")
    return 0


if __name__ == "__main__":
    sys.exit(main())

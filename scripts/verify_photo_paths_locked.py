# -*- coding: utf-8 -*-
"""Гейт: на стену уходит только то фото, что лежит в uploads.

Запуск: C:\\HVK\\.venv\\Scripts\\python.exe scripts\\verify_photo_paths_locked.py

Без LLM и без сети. Живой риск: ``_resolve_photo_paths`` принимала любой
абсолютный путь, а пути приходят от клиента — ``POST /publish`` читает
``photo_paths`` из тела запроса. В итоге по сети можно было указать файл
откуда угодно с диска и отправить его на стену от имени автора.

Провал = функция снова отдаёт файл, который не лежит внутри uploads,
или отдаёт не-картинку. Тогда автор может опубликовать на VK что угодно
из своей файловой системы.

Разрешено ровно одно: файлы внутри data/uploads с картинным расширением.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _uploads_dir() -> Path:
    """Каталог загрузок — тот же, что использует сам клиент VK."""
    from app.config import get_settings

    settings = get_settings()
    return settings.resolve_path(settings.uploads_path)


def test_outside_paths_rejected() -> None:
    """Путь снаружи uploads не проходит — даже если файл существует."""
    from app.vk.client import _resolve_photo_paths

    tmp = Path(tempfile.mkdtemp(prefix="hvk-outside-"))
    real = tmp / "secret.jpg"
    real.write_bytes(b"\xff\xd8\xff\xe0")

    assert _resolve_photo_paths([str(real)]) == [], "файл вне uploads принят"
    assert _resolve_photo_paths(["/etc/passwd"]) == []
    assert _resolve_photo_paths([r"C:\Windows\win.ini"]) == []
    assert _resolve_photo_paths([str(tmp / "..")]) == []

    # и явный обход через uploads
    uploads = _uploads_dir()
    assert _resolve_photo_paths([f"{uploads}/../../secret.jpg"]) == []


def test_non_photo_rejected() -> None:
    """В uploads может лежать не только фото — публиковать можно лишь картинки."""
    from app.vk.client import _resolve_photo_paths

    uploads = _uploads_dir()
    uploads.mkdir(parents=True, exist_ok=True)
    for name in ("note.txt", "script.py", "noext"):
        probe = uploads / name
        probe.write_text("x", encoding="utf-8")
        try:
            assert _resolve_photo_paths([str(probe)]) == [], f"{name} принят как фото"
        finally:
            probe.unlink(missing_ok=True)


def test_photo_inside_uploads_accepted() -> None:
    """Своё фото публиковать можно — иначе сломаем рабочий сценарий."""
    from app.vk.client import _resolve_photo_paths

    uploads = _uploads_dir()
    uploads.mkdir(parents=True, exist_ok=True)
    probe = uploads / "gate-check.jpg"
    probe.write_bytes(b"\xff\xd8\xff\xe0")
    try:
        got = _resolve_photo_paths([str(probe)])
        assert got == [probe.resolve()], got
        # и по имени, без полного пути
        assert _resolve_photo_paths(["gate-check.jpg"]) == [probe.resolve()]
    finally:
        probe.unlink(missing_ok=True)


def test_missing_and_empty() -> None:
    from app.vk.client import _resolve_photo_paths

    assert _resolve_photo_paths(None) == []
    assert _resolve_photo_paths([]) == []
    assert _resolve_photo_paths(["нет-такого.jpg"]) == []


def main() -> int:
    print("=== фото для публикации ===")
    problems = 0
    for name, fn in (
        ("путь вне uploads отклонён", test_outside_paths_rejected),
        ("не-фото отклонено", test_non_photo_rejected),
        ("фото из uploads проходит", test_photo_inside_uploads_accepted),
        ("пусто и отсутствующее", test_missing_and_empty),
    ):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            problems += 1
            print(f"ПРОВАЛ {name}: {type(exc).__name__}: {str(exc)[:200]}")
            continue
        print(f"ок    {name}")

    print()
    if problems:
        return 1
    print("ОК: на стену уйдут только фото из uploads")
    return 0


if __name__ == "__main__":
    sys.exit(main())

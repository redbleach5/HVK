# -*- coding: utf-8 -*-
"""Однократное скачивание ONNX-эмбеддера в data/models.

Источник — Xenova/multilingual-e5-small (ONNX-экспорт intmultilingual-e5).
Ничего не устанавливает в окружение: только файлы модели и токенизатора,
после этого поиск по архиву полностью локальный.
Скрипт идемпотентный: повторный запуск ничего не перекачивает.
"""
from __future__ import annotations

import shutil
import sys
import urllib.request
from pathlib import Path

BASE = "https://huggingface.co/Xenova/multilingual-e5-small/resolve/main"
FILES = {
    "onnx/model_quantized.onnx": "model.onnx",
    "tokenizer.json": "tokenizer.json",
}

MIN_SIZE = 500_000  # меньше — значит битый/частичный файл


def fetch(url: str, dst: Path) -> None:
    tmp = dst.with_name(dst.name + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "HVK/1.0"})
    with urllib.request.urlopen(req, timeout=180) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out)
    if tmp.stat().st_size < MIN_SIZE:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"файл подозрительно мал: {url}")
    tmp.replace(dst)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    target = root / "data" / "models" / "e5-small-onnx"
    target.mkdir(parents=True, exist_ok=True)
    print(f"папка: {target}")
    for src, name in FILES.items():
        dst = target / name
        if dst.exists() and dst.stat().st_size >= MIN_SIZE:
            print(f"skip {name}: уже на месте ({dst.stat().st_size} байт)")
            continue
        url = f"{BASE}/{src}"
        print(f"качаю {url}")
        fetch(url, dst)
        print(f"ок: {name} = {dst.stat().st_size} байт")
    print("готово — эмбеддер готов к работе")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Гейт: приватный архив не должен утекать чужому сайту в браузере.

Запуск: C:\\HVK\\.venv\\Scripts\\python.exe scripts\\verify_cors_locked.py

Без LLM и без сети. Живой сбой: CORS стоял как
``allow_origins=["*"]`` вместе с ``allow_credentials=True``.
Starlette в этом случае отражает Origin запроса, поэтому любой сайт,
открытый в браузере автора, мог прочитать её посты, черновики,
аналитику и историю чата обычным fetch на http://127.0.0.1:8080 —
с браузера это считается «локальным» адресом.

Продукту CORS не нужен: SPA ходит в /api на :8501 (same-origin), а тот
проксирует на :8080. Поэтому правильная настройка — не добавлять
CORSMiddleware вовсе.

Провал = в app/main.py снова появился CORS со звёздочкой или с
allow_credentials. Тогда архив автора снова утечёт любому сайту.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Чужие origin, которыми мы проверяем отражание.
FOREIGN_ORIGINS = (
    "https://evil.example",
    "http://localhost:1337",
    "null",
)


def _check_source() -> None:
    """В коде не должно быть разрешающего CORS."""
    src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    if 'allow_origins=["*"]' in src.replace(" ", "").replace('allow_origins = ["*"]', 'allow_origins=["*"]'):
        raise SystemExit("app/main.py: allow_origins=['*'] — архив снова утечёт чужому сайту")
    if "CORSMiddleware" in src:
        raise SystemExit(
            "app/main.py: CORSMiddleware вернулся. SPA ходит через /api на :8501 "
            "(same-origin), проксирует ui/static_server.py — CORS не нужен"
        )


def _check_behaviour() -> None:
    """Поведение важнее исходника: Origin не должен отражаться."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    # TestClient без контекст-менеджера: lifespan не поднимается,
    # БД, планировщик и фоновый воркер не трогаются.
    client = TestClient(create_app())

    for origin in FOREIGN_ORIGINS:
        response = client.get("/health", headers={"Origin": origin})
        allowed = response.headers.get("access-control-allow-origin")
        if allowed:
            raise SystemExit(
                f"Origin {origin!r} отражён как {allowed!r} — "
                "браузер автора отдаст архив любому сайту"
            )
        credentials = response.headers.get("access-control-allow-credentials")
        if credentials:
            raise SystemExit(f"Отдан Access-Control-Allow-Credentials при Origin {origin!r}")

    # Штатный путь SPA: same-origin через прокси. Он обязан работать.
    response = client.get("/health")
    if response.status_code != 200:
        raise SystemExit(f"/health вернул {response.status_code}, а не 200")

    client.close()


def main() -> int:
    print("=== приватность: Origin не отражается ===")
    for name, fn in (("исходник без CORS", _check_source), ("поведение", _check_behaviour)):
        try:
            fn()
        except SystemExit as exc:
            print(f"ПРОВАЛ {name}: {exc}")
            return 1
        except Exception as exc:  # noqa: BLE001
            print(f"ПРОВАЛ {name}: {type(exc).__name__}: {exc}")
            return 1
        print(f"ок    {name}")
    print()
    print("ОК: чужой сайт в браузере не прочитает архив; SPA через /api работает")
    return 0


if __name__ == "__main__":
    sys.exit(main())

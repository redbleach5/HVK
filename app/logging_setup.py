"""Настройка логирования приложения."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import ROOT_DIR


def setup_logging(level: int = logging.INFO) -> None:
    """Консоль + app.log + chat.log (стрим, LLM, маршруты чата)."""
    log_dir = ROOT_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

    for name, filename, max_bytes in (
        ("app", "app.log", 4_000_000),
        ("chat", "chat.log", 4_000_000),
    ):
        handler = RotatingFileHandler(
            log_dir / filename,
            encoding="utf-8",
            maxBytes=max_bytes,
            backupCount=3,
        )
        handler.setFormatter(formatter)
        if name == "chat":
            handler.addFilter(
                lambda record: record.name.startswith(
                    (
                        "app.agents.chat",
                        "app.llm.client",
                        "app.api.routes.chat",
                        "app.web.search",
                    )
                )
            )
        root.addHandler(handler)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)

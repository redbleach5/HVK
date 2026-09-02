# -*- coding: utf-8 -*-
"""Мониторинг api.log + ui.log в реальном времени."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = [ROOT / "logs" / "api.log", ROOT / "logs" / "ui.log"]
DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 300
INTERVAL = 1.5

HIGHLIGHT = (
    "error",
    "exception",
    "traceback",
    "500",
    "422",
    "chat/stream",
    "chat/history",
    "modelasleep",
    "llmresponse",
    "warning",
    "idle:",
)


def _safe_print(text: str) -> None:
    enc = sys.stdout.encoding or "utf-8"
    out = text.encode(enc, errors="replace").decode(enc, errors="replace")
    print(out, flush=True)


def main() -> None:
    offsets: dict[Path, int] = {}
    for path in LOGS:
        if path.is_file():
            offsets[path] = path.stat().st_size
        else:
            offsets[path] = 0
            _safe_print(f"[watch] missing: {path.name}")

    _safe_print(f"[watch] started for {DURATION}s — {', '.join(p.name for p in LOGS)}")
    t_end = time.time() + DURATION

    while time.time() < t_end:
        for path in LOGS:
            if not path.is_file():
                continue
            try:
                with path.open("r", encoding="utf-8", errors="replace") as fh:
                    fh.seek(offsets.get(path, 0))
                    chunk = fh.read()
                    offsets[path] = fh.tell()
            except OSError as exc:
                _safe_print(f"[watch] read error {path.name}: {exc}")
                continue

            if not chunk:
                continue
            for raw in chunk.splitlines():
                line = raw.rstrip()
                if not line:
                    continue
                low = line.lower()
                tag = "!" if any(h in low for h in HIGHLIGHT) else " "
                _safe_print(f"{tag} [{path.name}] {line}")

        time.sleep(INTERVAL)

    _safe_print(f"[watch] done after {DURATION}s")


if __name__ == "__main__":
    main()

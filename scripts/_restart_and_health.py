# -*- coding: utf-8 -*-
"""Детачнутый перезапуск API+UI и health-проверка с ретраями.

Результат пишет в logs/f_health.log — чтение не зависит от shell integration.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
LOGS = ROOT / "logs"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DETACHED = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def kill_port(port: int) -> None:
    out = subprocess.run(
        ["cmd", "/c", f"netstat -ano | findstr :{port} | findstr LISTENING"],
        capture_output=True, text=True,
    ).stdout
    for line in out.splitlines():
        parts = line.split()
        if parts and parts[-1].isdigit():
            subprocess.run(["taskkill", "/PID", parts[-1], "/F"], capture_output=True)


def main() -> int:
    for port in (8080, 8501):
        kill_port(port)
    time.sleep(2)

    api_log = open(LOGS / "api.log", "ab")
    ui_log = open(LOGS / "ui.log", "ab")
    subprocess.Popen(
        [PY, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8080"],
        cwd=str(ROOT), stdout=api_log, stderr=subprocess.STDOUT,
        creationflags=DETACHED,
    )
    subprocess.Popen(
        [PY, "-m", "uvicorn", "ui.static_server:app", "--host", "0.0.0.0", "--port", "8501"],
        cwd=str(ROOT), stdout=ui_log, stderr=subprocess.STDOUT,
        creationflags=DETACHED,
    )

    import httpx

    deadline = time.time() + 90
    health = None
    while time.time() < deadline:
        time.sleep(3)
        try:
            resp = httpx.get("http://127.0.0.1:8080/health", timeout=5)
            health = f"status={resp.status_code} {resp.text[:300]}"
            break
        except Exception as exc:  # noqa: BLE001
            health = f"pending: {exc}"

    with open(LOGS / "f_health.log", "w", encoding="utf-8") as fh:
        fh.write(f"{time.strftime('%H:%M:%S')} {health}\n")
    print("HEALTH_WRITTEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())

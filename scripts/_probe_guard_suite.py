# -*- coding: utf-8 -*-
"""Прогон стражей verify_* с сохранением вывода в logs\\guard_<имя>.txt.

Запуск:
    .venv\\Scripts\\python.exe scripts\\_probe_guard_suite.py verify_chat_live verify_vk
    .venv\\Scripts\\python.exe scripts\\_probe_guard_suite.py --group llm

Зачем: вывод стражей длинный и с кириллицей, а окно терминала теряет его при
долгом прогоне. Здесь каждый страж пишет свой лог, а в конце — сводная таблица
(код выхода, время, последняя значимая строка) в logs\\guard_suite.txt.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
PY = ROOT / ".venv" / "Scripts" / "python.exe"

# Стражи, которые зовут модель: долгие, но именно они ловят деградацию качества.
LLM = [
    "verify_retrieval_scoring",
    "verify_russian_retrieval",
    "verify_keyword_morphology",
    "verify_intent_route",
    "verify_archive_library",
    "verify_grounding",
    "verify_working_context",
    "verify_voice_in_prompt",
    "verify_think_budget",
    "verify_think_stream",
    "verify_web_search",
    "verify_agents_practice",
    "verify_chat_live",
]
OFFLINE = [
    "verify_archive_core",
    "verify_author_question",
    "verify_chat_api_search",
    "verify_chat_large",
    "verify_chat_threads",
    "verify_context_spend",
    "verify_desk",
    "verify_diagnostics",
    "verify_frontend_chat",
    "verify_idle_worker",
    "verify_json_schemas",
    "verify_roi_chat",
    "verify_ui_pass",
    "verify_vk",
    "verify_vk_methods",
]


def run(names: list[str]) -> int:
    rows: list[tuple[str, int, float, str]] = []
    for name in names:
        script = ROOT / "scripts" / f"{name}.py"
        if not script.exists():
            rows.append((name, 127, 0.0, "нет такого стража"))
            continue
        t0 = time.time()
        try:
            done = subprocess.run(
                [str(PY), "-X", "utf8", str(script)],
                cwd=str(ROOT),
                capture_output=True,
                timeout=1500,
            )
            out = (done.stdout + done.stderr).decode("utf-8", "replace")
            code = done.returncode
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or b"").decode("utf-8", "replace") + "\n[таймаут 1500с]"
            code = 124
        dt = time.time() - t0
        (LOGS / f"guard_{name}.txt").write_text(out, encoding="utf-8")
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        tail = lines[-1][:110] if lines else "(пусто)"
        rows.append((name, code, dt, tail))

    report = ["Страж                          Код   Сек  Последняя строка", "-" * 100]
    for name, code, dt, tail in rows:
        report.append(f"{name:<30} {code:>3} {dt:>6.1f}  {tail}")
    bad = [r for r in rows if r[1] != 0]
    report.append("")
    report.append(f"итог: провалов {len(bad)} из {len(rows)}")
    for name, code, _dt, tail in bad:
        report.append(f"  ПРОВАЛ {name} (код {code}): {tail}")
    text = "\n".join(report)
    (LOGS / "guard_suite.txt").write_text(text, encoding="utf-8")
    print(text)
    return 1 if bad else 0


def main() -> int:
    args = sys.argv[1:]
    if not args:
        names = OFFLINE
    elif args[0] == "--group" and len(args) > 1:
        names = LLM if args[1] == "llm" else OFFLINE
    else:
        names = args
    return run(names)


if __name__ == "__main__":
    sys.exit(main())
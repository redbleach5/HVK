# -*- coding: utf-8 -*-
"""Коммит + пуш HVK: личность берём из истории репо (локально), лог в UTF-8.

Не трогает глобальный git-config. Пушит только если коммит удался.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "git_final.log"
MSG = ROOT / "logs" / "commit_msg.txt"


def run(args: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def main() -> int:
    lines: list[str] = []

    def log(text: str = "") -> None:
        lines.append(text)
        print(text, flush=True)

    code, who = run(["log", "-1", "--format=%an%x09%ae"])
    log(f"== last-commit author (exit {code}) ==")
    log(who or "(пусто)")

    if code == 0 and "\t" in who:
        name, email = who.split("\t", 1)
        # Пробел в имени допустим; запятая в email — нет.
        c1, out1 = run(["config", "user.name", name.strip()])
        c2, out2 = run(["config", "user.email", email.strip()])
        log(f"== local identity set: {name.strip()} <{email.strip()}> "
            f"(exit {c1}/{c2}) ==")

    code, out = run(["commit", "-F", str(MSG)])
    log(f"== commit (exit {code}) ==")
    log(out[-1500:] if out else "(без вывода)")
    if code != 0:
        log("ИТОГ: коммит не удался — пуш не выполнял.")
        LOG.write_text("\n".join(lines), encoding="utf-8")
        return 1

    code, out = run(["push", "origin", "main"])
    log(f"== push origin main (exit {code}) ==")
    log(out[-1500:] if out else "(без вывода)")

    _, head = run(["log", "-1", "--oneline"])
    _, status = run(["status", "-sb"])
    log("== head ==")
    log(head)
    log("== status ==")
    log(status)

    ok = code == 0
    log(f"ИТОГ: {'ОК — закоммичено и запушено' if ok else 'ПРОВАЛ пуша'}")
    LOG.write_text("\n".join(lines), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Вырезка из api.log вокруг ошибок валидации why.related_posts.

Запуск: C:\\HVK\\.venv\\Scripts\\python.exe scripts\\_probe_edit_502.py
Только читает logs/api.log.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "logs" / "api.log"

lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines()
pattern = re.compile(r"why\.related_posts|text/edit|502")
hits = [i for i, line in enumerate(lines) if pattern.search(line)]
print(f"совпадений: {len(hits)}")
for i in hits[-4:]:
    start = max(0, i - 25)
    print("-" * 60)
    for line in lines[start : i + 3]:
        print(line[:300])
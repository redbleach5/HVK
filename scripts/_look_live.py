# -*- coding: utf-8 -*-
"""One live screenshot of Streamlit as it is now. No desk mutation."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "scripts"))
from _shot_cdp import shot  # noqa: E402

OUT = ROOT / "scripts" / "_shots" / "live_chat.png"


async def main() -> None:
    report = await shot("live_chat", "http://127.0.0.1:8501/", "Тихая редакция", timeout_s=35.0)
    print("ok", report.get("has_needle"), "bytes", report.get("png_bytes"), "err", report.get("error") or "-")
    sample = (report.get("text_sample") or "")[:240]
    (ROOT / "scripts" / "_shots" / "live_chat.txt").write_text(sample, encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())

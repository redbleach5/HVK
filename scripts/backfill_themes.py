"""Tag archive themes and open the desk if posts are already in."""

from __future__ import annotations

import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.memory.themes import infer_theme  # noqa: E402


def main() -> None:
    db = ROOT / "data" / "app.db"
    con = sqlite3.connect(db)
    rows = con.execute("select id, text, theme from posts").fetchall()
    counts: Counter[str] = Counter()
    for pid, text, theme in rows:
        if (theme or "").strip():
            counts[theme] += 1
            continue
        new = infer_theme(text or "")
        con.execute("update posts set theme = ? where id = ?", (new, pid))
        counts[new] += 1
    n = con.execute("select count(*) from posts").fetchone()[0]
    voice = con.execute("select count(*) from voice_profiles").fetchone()[0]
    if n >= 2:
        con.execute(
            "update author_profile set onboarding_done = 1, onboarding_step = 3 where id = 1"
        )
    con.commit()
    print("posts", n, "voice", voice)
    print("themes", dict(counts.most_common()))
    con.close()


if __name__ == "__main__":
    main()

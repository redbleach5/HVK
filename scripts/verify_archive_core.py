"""Проверка ядра архива: цитаты, индекс, статус API. Не трогает базу вслепую."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
THOUGHTS = ROOT / "THOUGHTS.txt"
API = "http://127.0.0.1:8080"

sys.path.insert(0, str(ROOT))

from app.db.models import Post
from app.memory.citations import digest_cites_posts, digest_from_posts, post_citation


def _report(lines: list[str]) -> None:
    block = "\n".join(lines) + "\n"
    prev = THOUGHTS.read_text(encoding="utf-8") if THOUGHTS.exists() else ""
    THOUGHTS.write_text(prev + block, encoding="utf-8")


def _citations_ok() -> list[str]:
    posts = [
        Post(
            id=1,
            text="Утром заварила чай в любимой чашке — пар, тишина, свет на столе.",
        ),
        Post(
            id=2,
            text="Нашла на блошином рынке льняную салфетку. Дома легла как будто всегда здесь жила.",
        ),
    ]
    cite = post_citation(posts[0])
    body, highs = digest_from_posts(posts)
    generic = "Сегодня хорошая погода для контента в блоге"
    checks = [
        ("citation_has_tea", "чай" in cite.lower()),
        ("digest_has_tea", "чай" in body.lower()),
        ("digest_has_napkin", "салфет" in body.lower()),
        ("digest_cites_archive", digest_cites_posts(body, posts)),
        ("generic_does_not_cite", not digest_cites_posts(generic, posts)),
        ("highlights_n", len(highs) == 2),
    ]
    return [f"{name}: {'yes' if ok else 'NO'}" for name, ok in checks]


def main() -> int:
    lines = [
        "",
        "## REPORT verify_archive_core.py",
        f"time: {datetime.now().isoformat(timespec='seconds')}",
        "runner: C:\\HVK\\scripts\\verify_archive_core.py",
    ]
    lines.extend(_citations_ok())
    failed = any(row.endswith(": NO") for row in lines)

    try:
        with httpx.Client(base_url=API, timeout=httpx.Timeout(5.0, read=20.0)) as client:
            status = client.get("/onboarding/status")
            st = status.json()
            lines.append(f"posts_imported: {st.get('posts_imported')}")
            lines.append(f"voice_ready: {st.get('voice_ready')}")
            lines.append(f"onboarding_done: {st.get('done')}")
            today = client.get("/today")
            data = today.json()
            digest = data.get("digest") or ""
            related = (data.get("why") or {}).get("related_posts") or []
            lines.append(f"today_related_posts: {len(related)}")
            if int(st.get("posts_imported") or 0) >= 2:
                lines.append(f"today_has_related: {'yes' if related else 'NO'}")
            else:
                bad = client.post("/onboarding/complete")
                lines.append(f"complete_without_archive: {bad.status_code}")
    except Exception as exc:
        lines.append(f"api: {type(exc).__name__}: {exc}")

    _report(lines)
    print("\n".join(lines))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

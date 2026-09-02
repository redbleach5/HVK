# -*- coding: utf-8 -*-
"""Проверка API диалогов чата."""
from __future__ import annotations

import httpx

API = "http://127.0.0.1:8080"


def main() -> None:
    with httpx.Client(base_url=API, timeout=30.0) as c:
        r = c.get("/health")
        r.raise_for_status()
        threads = c.get("/chat/threads").json()
        print("threads:", len(threads.get("threads", [])))
        hist = c.get("/chat/history").json()
        print("history thread_id:", hist.get("thread_id"), "msgs:", len(hist.get("messages", [])))
        created = c.post("/chat/threads", json={}).json()
        print("created:", created["id"], created["title"])
        after = c.get("/chat/threads").json()
        print("threads after create:", len(after["threads"]))
        dr = c.delete(f"/chat/threads/{created['id']}")
        dr.raise_for_status()
        print("delete:", dr.status_code)
    print("THREADS OK")


if __name__ == "__main__":
    main()

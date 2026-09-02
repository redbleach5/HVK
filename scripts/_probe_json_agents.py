# -*- coding: utf-8 -*-
"""Probe JSON agents timing after prompt trim."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

API = "http://127.0.0.1:8080"


def probe(name: str, method: str, path: str, **kwargs) -> None:
    t0 = time.time()
    try:
        with httpx.Client(base_url=API, timeout=httpx.Timeout(600.0, connect=15.0)) as client:
            if method == "POST":
                r = client.post(path, **kwargs)
            else:
                r = client.get(path, **kwargs)
        dt = time.time() - t0
        print(f"{name}: {r.status_code} in {dt:.1f}s")
        if r.status_code >= 400:
            print(r.text[:300])
    except Exception as exc:
        print(f"{name}: FAIL after {time.time() - t0:.1f}s — {exc}")


def main() -> None:
    probe("health", "GET", "/health")
    probe("ideas_generate", "POST", "/ideas/generate", json={"count": 2})
    probe("analytics_report", "GET", "/analytics", params={"with_report": "true"})


if __name__ == "__main__":
    main()

---
name: solve-dont-thrash
description: >
  How to finish a coding task with local Ollama: diagnose once, change the
  product, verify once. Use when stuck in retries, timeouts, pip, or wiping data.
triggers:
  - timeout
  - retry
  - stuck
  - pip install
  - wipe
  - hang
  - Start-Process
  - python -c
---

# Solve, don't thrash

Local models are slow. A 30–90s Ollama call is normal, not a hang.

1. Name the bug in one sentence. Change the product to fix that bug.
2. Verify **once**: write a `.py` file with `file_editor`, run project venv Python.
3. If a request is slow, `GET` status or read server logs. Do **not** kill the process, do **not** delete the database, do **not** start a second server.
4. Do not `pip install` to escape an import error — use the project's `.venv`.
5. PowerShell: one command per call; no `&&`; no `python -c` with non-ASCII.
6. When it works, stop. Report files changed. Do not loop.

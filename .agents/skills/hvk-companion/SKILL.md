---
name: hvk-companion
description: >
  Тихая редакция: assistant not ghostwriter. Memory from VK or pasted posts.
  Use for onboarding, voice, chat ideas/today/edit, Streamlit, start.bat.
  Also: how to debug HVK without killing the API or wiping the database.
triggers:
  - hvk
  - vk
  - streamlit
  - "8501"
  - "8080"
  - редакция
  - ollama
  - onboarding
  - start.bat
  - голос
  - архив
---

# HVK — Тихая редакция

Assistant for the VK blog «Красивое в обычном». **Do not write posts for her.** Every suggestion needs «почему».

Without posts in SQLite (`data/app.db`), the product is a generic chat — that is the bug to fix. Prefer `POST /onboarding/archive` when VK is not configured. That endpoint saves posts immediately; voice builds in the background. Poll `GET /onboarding/status`. Never mention `.env` in the UI.

## Solve, don't thrash

- Use `C:\HVK\.venv\Scripts\python.exe` only. Do not pip. Do not sandbox Python.
- Slow LLM ≠ failure. Never kill `:8080` mid-request. Never delete `data/app.db` to make a test green.
- Scripts: `file_editor` → `.py` file. No `python -c` with Russian text in PowerShell.
- Port **8000** is Canvas. Restart only HVK API/UI. Canvas now self-restarts a hung agent-server; do not kill `:8000` to "fix" a stuck chat.
- Group VK token: inbox. Wall import needs `VK_WALL_TOKEN` (admin user); then the service paginates the full wall. Paste still works.
- The RX 7700 XT PC is **off**. Brain and eyes = local `qwen3.8:27b` (vision). Do not load `gemma4:12b` on this PC. Do not wait on `192.168.178.115`. Chat: stream thinking. JSON tools: `think: false`.

`think: false` on completions. Never print tokens.

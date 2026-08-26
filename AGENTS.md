# Тихая редакция (HVK)

Windows `C:\HVK`. Streamlit `:8501`, FastAPI `:8080`, Ollama `http://127.0.0.1:11434/v1`.
**Port 8000 is Agent Canvas — never bind or kill it.** Restart only HVK API/UI.

## Product

Assistant for the VK lifestyle blog «Красивое в обычном», **not a ghostwriter**.
Smart core = her archive in SQLite (`data/app.db`): voice, preferences, lessons, antipathies, rhythm, «почему» on every suggestion.
Without her posts, ideas/today/editor must refuse honestly — not hallucinate a companion.

## Must keep true

- Onboarding: VK import **or** paste 3–8 posts (`POST /onboarding/archive` saves first, voice builds in background). Poll `GET /onboarding/status`.
- Archive can be added after onboarding. Do not finish onboarding with empty archive.
- Chat / ideas / today / editor cite her texts. Feedback teaches memory.
- Author is not a programmer: **never** mention `.env`, ports, Ollama, GGUF, llama.cpp in the UI.
- VK/Telegram optional. Group token may do ЛС but not wall — set `VK_WALL_TOKEN` (admin user) to import the full wall. Paste archive still works.

## Engineering

- Brain `qwen3.8:27b` on this PC (5060 Ti + 3060), quality over speed. Chat streams thinking in «размышляю», then the reply. Do not cut a live thought with a short timeout. JSON agents (ideas/photo/voice) keep `think: false`. While 7700 XT is off, eyes = the same model. Do not load `gemma4:12b` here.
- Python only `C:\HVK\.venv\Scripts\python.exe`. PowerShell. No pip into sandbox/system.
- Layout: `app/`, `ui/`, `bot/`, `scripts\start.bat`.
- Streamlit puts `ui/` on `sys.path` — never let `import app` resolve to `ui/app.py`.
- Slow Ollama ≠ crash. Do not kill `:8080` mid-request, do not wipe `data/app.db`, do not start a second API.
- One fix, one verify. Prefer a `.py` script over `python -c` with Cyrillic.

# Тихая редакция (HVK)

Windows `C:\HVK`. React SPA `:8501`, FastAPI `:8080`, Ollama `http://127.0.0.1:11434/v1`.
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

- Brain `qwen3.8:27b` on this PC (5060 Ti + 3060), quality over speed. Chat streams thinking in «размышляю», then the reply. Do not cut a live thought with a short timeout. JSON agents (ideas/photo/voice) keep `think: false`. While 7700 XT is off, eyes = the same model. Do not load `gemma4:12b` here. LLM-клиент держит мозг резидентным (`llm_keep_alive=30m` в config — без него 27B выгружается и каждый ход начинается с минутной холодной загрузки) и на ретрае JSON поднимает temperature (+0.15, потолок 0.85), а не роняет до детерминированных 0.1. Латентность JSON-пути: `scripts/_probe_editor_latency.py` (тёплый вызов ~4с).
- Python only `C:\HVK\.venv\Scripts\python.exe`. PowerShell. No pip into sandbox/system.
- Retrieval: локальный e5-эмбеддер (onnxruntime, `data/models/e5-small-onnx`) в Chroma-коллекции `author_posts_e5`; папки с моделью нет → прежняя MiniLM и коллекция `author_posts`. Скрипты: `scripts/fetch_e5_onnx.py` (скачать раз), `scripts/migrate_chroma_e5.py` (переиндекс), `scripts/verify_russian_retrieval.py` (сравнение со старой MiniLM). Веса слоёв в `app/memory/retrieve.py`: `_SEM_MULT`/`_KEY_WEIGHT` (семантика e5 доминирует над случайным ключом; калибровка и контроль — `scripts/_probe_retrieval_weights.py`, `scripts/verify_retrieval_scoring.py`).
- Контекст агентов: `ContextEngine.pack/build` и `pack_for_agent` принимают `with_session` (рабочий набор чата; `False` у идей/редактора/фото/аудита/консьержа — чужой диалог не утекает в их промпт) и `include_voice` (`False` у редактора, который показывает полный профиль голоса отдельно). Дубли «хитов» с блоком «ПО ЭТОМУ ВОПРОСУ» исключены. Зонд расхода: `scripts/_probe_context_spend.py static|talk` (замер реальных токенов Ollama и проверка цитат вне контекста). Страж, который не даст контекст-правкам выползти обратно: `scripts/verify_context_spend.py` (без LLM).
- Layout: `app/`, `frontend/`, `ui/static_server.py`, `bot/`, `scripts\start.bat`.
- Legacy Streamlit UI in `ui/_legacy_streamlit/` (не запускать).
- Slow Ollama ≠ crash. Do not kill `:8080` mid-request, do not wipe `data/app.db`, do not start a second API.
- One fix, one verify. Prefer a `.py` script over `python -c` with Cyrillic.

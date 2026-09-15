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

- Brain `qwen3.6:latest` on this PC (5060 Ti 16 ГБ + 64 ГБ RAM), MoE 35B-A3B: тот же класс качества, что 27B, но ~5× быстрее (тёплый JSON-вызов ~1с), vision, мысли стримит отдельным полем, `think:false` отдаёт чистый JSON. Chat streams thinking in «размышляю», then the reply. Do not cut a live thought with a short timeout (у qwen3.6 мысль длинная: бюджет генерации в клиенте обязателен, `num_predict` не снимать). JSON agents (ideas/photo/voice) keep `think: false`. While 7700 XT is off, eyes = the same model. Do not load `gemma4:12b` and `qwen3.8-flash-next` (79.8 ГБ — не влезает в 16 ГБ VRAM + 52 ГБ RAM) here. LLM-клиент держит мозг резидентным (`llm_keep_alive=30m` в config — без него каждый ход начинается с холодной загрузки) и на ретрае JSON поднимает temperature (+0.15, потолок 0.85), а не роняет до детерминированных 0.1. Латентность JSON-пути: `scripts/_probe_editor_latency.py` (тёплый вызов ~1с).
- Python only `C:\HVK\.venv\Scripts\python.exe`. PowerShell. No pip into sandbox/system.
- Retrieval: эмбеддер Ollama `nomic-embed-text-v2-moe` (768-dim, русский) в Chroma-коллекции `author_posts_nomic`; длинные посты кладутся кусками (700 симв., перекрытие 100, `upsert_post`), поиск дедуплицируется по посту (лучший кусок). Ollama с этой моделью недоступна → прежний e5 (`data/models/e5-small-onnx`, коллекция `author_posts_e5`), его нет → legacy MiniLM (`author_posts`). Режим/эмбеддер согласованы в `app/memory/embedder.py` (`active_mode`). Переиндекс: `scripts/migrate_chroma_nomic.py` (один раз; старые коллекции не трогаются — откат это выключить Ollama-модель). Веса слоёв в `app/memory/retrieve.py`: `_SEM_MULT`/`_KEY_WEIGHT`/`_ENGAGE_MULT` (200 — вовлечённость лишь тай-брейк) и `_KEY_RARE_BOOST` (IDF-lite: редкий ключ весит больше частого); слои в `add()` всегда суммируются с демпфом 0.35 — пост с сильными обоими слоями не теряет семантику. Гейт: `scripts/verify_retrieval_scoring.py` (самопоиск@3 15/15, темы гардероб/рецепт/доч). Сравнение e5-vs-legacy: `scripts/verify_russian_retrieval.py`.
- Контекст агентов: `ContextEngine.pack/build` и `pack_for_agent` принимают `with_session` (рабочий набор чата; `False` у идей/редактора/фото/аудита/консьержа — чужой диалог не утекает в их промпт) и `include_voice` (`False` у редактора, который показывает полный профиль голоса отдельно). Дубли «хитов» с блоком «ПО ЭТОМУ ВОПРОСУ» исключены. Зонд расхода: `scripts/_probe_context_spend.py static|talk` (замер реальных токенов Ollama и проверка цитат вне контекста). Страж, который не даст контекст-правкам выползти обратно: `scripts/verify_context_spend.py` (без LLM).
- Layout: `app/`, `frontend/`, `ui/static_server.py`, `bot/`, `scripts\start.bat`.
- Legacy Streamlit UI in `ui/_legacy_streamlit/` (не запускать).
- Slow Ollama ≠ crash. Do not kill `:8080` mid-request, do not wipe `data/app.db`, do not start a second API.
- One fix, one verify. Prefer a `.py` script over `python -c` with Cyrillic.

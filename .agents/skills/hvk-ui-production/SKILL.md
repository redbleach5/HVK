---
name: hvk-ui-production
description: >
  Production-level Streamlit UI for Тихая редакция. Warm beige magazine,
  Claude-like chat shell. Use when editing ui/, theme, onboarding, cards.
triggers:
  - streamlit
  - "8501"
  - интерфейс
  - вкладк
  - theme.py
  - pages_view
  - chat_view
  - продакшен
  - UI
  - дашборд
  - чат
---

# HVK UI — production bar

Author is not a programmer. The screen must feel like Claude chat + a quiet lifestyle desk — not an admin panel or a tab dashboard.

## Do this

Edit only `C:\HVK\ui\` (`app.py`, `theme.py`, `pages_view.py`, `chat_view.py`). CSS in `theme.py`. Streamlit hot-reloads — do not kill `:8501` or `:8080` unless the UI process is actually dead.

## Must look like a product

- **Shell:** home = chat (Claude-like). Left sidebar = «Диалог» + «Стол» (Сегодня, Фото, Текст, Идеи и план, Аналитика, ЛС if VK). No top pills / radio tabs.
- Desk pages: secondary «← к диалогу» via `desk_back_to_chat()`. Default `main_nav` = «Чат».
- Chat empty state: centered title + «Чем помочь сегодня?» + 3–4 quiet secondary chips (not navigation pills). `st.chat_input` at bottom. Photo upload in a quiet expander.
- Cards: real bordered containers around idea/today/plan items. Do not wrap widgets with broken `card_start`/`card_end` markdown divs.
- Photo: show thumbnails **before** «разобрать».
- Analytics: numbers/chart first; LLM-отчёт only on a button. Never block on `/analytics?with_report=true`.
- Feedback: «учту» / «не соглашусь», not «принять» / «отклонить».
- Week plan: seven-day grid, not a stack of expanders.
- Concierge/ЛС only if VK is connected; otherwise omit.
- Dates: `st.date_input`, not free-text ГГГГ-ММ-ДД.
- Empty states: full editorial pause, not a grey caption.
- Never mention `.env`, ports, Ollama, GGUF, llama.cpp, API.

## Verify once

`GET http://127.0.0.1:8080/health` and `GET /onboarding/status`. Open `http://127.0.0.1:8501`. If Streamlit did not pick up CSS, restart **only** the Streamlit window, never Canvas `:8000`.

## Stop when

Chat is the home screen, sidebar opens desk tools, and flows still work (today → idea → draft → text).

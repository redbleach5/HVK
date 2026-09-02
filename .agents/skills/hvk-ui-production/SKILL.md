---
name: hvk-ui-production
description: >
  Production-level React UI for Тихая редакция. Warm beige magazine,
  Claude-like chat shell. Use when editing frontend/, static_server, onboarding, cards.
triggers:
  - react
  - typescript
  - frontend
  - "8501"
  - интерфейс
  - продакшен
  - UI
  - дашборд
  - чат
---

# HVK UI — production bar

Author is not a programmer. The screen must feel like Claude chat + a quiet lifestyle desk — not an admin panel or a tab dashboard.

## Do this

Edit `C:\HVK\frontend\src\` (pages, chat, layout, theme). Styles in `frontend/src/theme/`. After changes: `cd frontend && npm run build`. UI served by `ui/static_server.py` on `:8501`. Do not kill `:8080` mid-request.

Legacy Streamlit is in `ui/_legacy_streamlit/` — do not extend.

## Must look like a product

- **Shell:** home = chat (Claude-like). Left sidebar = «Диалог» + «Стол» (Сегодня, Фото, Текст, Идеи и план, Аналитика, ЛС if VK).
- Desk pages: «← к диалогу» link. Chat is `/`.
- Chat: empty state chips, streaming «размышляю», composer at bottom with photo attach.
- Cards: bordered `.card` containers in chat and desk.
- Photo: thumbnails before «разобрать».
- Analytics: chart first; report only on button (`with_report=true`).
- Feedback: «учту» / «не соглашусь».
- Week plan: seven-day grid in IdeasPage.
- Never mention `.env`, ports, Ollama, GGUF, llama.cpp, API in UI copy.

## Verify once

`GET http://127.0.0.1:8080/health`. `npm run build` in frontend. `scripts/verify_ui_pass.py`. Open `http://127.0.0.1:8501`.

## Stop when

Chat is home, sidebar opens desk tools, flows work (today → idea → draft → text).

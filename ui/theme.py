"""Стили и общие виджеты интерфейса — тёплый стол, не админка Streamlit."""

from __future__ import annotations

import streamlit as st

from ui.api_client import api_get, api_post, friendly_error, vk_is_configured

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600&family=Source+Sans+3:wght@400;500;600&display=swap');

:root {
  --ink: #3d3229;
  --muted: #7a6a5c;
  --line: #e6dcd0;
  --bg: #FAF8F5;
  --panel: #fffaf4;
  --accent: #8B7355;
  --accent-hover: #6f5b43;
  --soft: #f4eee7;
}

html, body, .stApp, [data-testid="stAppViewContainer"] {
  background: var(--bg) !important;
  color: var(--ink);
  font-family: "Source Sans 3", "Segoe UI", sans-serif !important;
}

[data-testid="stHeader"] {
  background: transparent !important;
  height: 0 !important;
}
#MainMenu, footer, [data-testid="stToolbar"],
[data-testid="stDecoration"], [data-testid="stStatusWidget"],
.stDeployButton, div[data-testid="stAppDeployButton"],
[data-testid="stBaseButton-headerNoPadding"] {
  display: none !important;
}

.block-container {
  padding-top: 1.2rem !important;
  padding-bottom: 5.5rem !important;
  max-width: 740px !important;
}

h1, h2, h3, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
  font-family: "Source Serif 4", Georgia, "Times New Roman", serif !important;
  color: var(--ink) !important;
  font-weight: 500 !important;
  letter-spacing: -0.015em;
}

/* Сайдбар — тихий рельс как у Claude */
[data-testid="stSidebar"] {
  background: #f3ebe3 !important;
  border-right: 1px solid var(--line);
}
[data-testid="stSidebar"] .block-container {
  padding-top: 1.2rem !important;
  padding-bottom: 1.5rem !important;
}
[data-testid="stSidebar"] * {
  font-family: "Source Sans 3", "Segoe UI", sans-serif !important;
}
.tr-side-brand {
  font-family: "Source Serif 4", Georgia, serif !important;
  font-size: 1.2rem;
  font-weight: 500;
  color: var(--ink);
  margin: 0 0 0.15rem 0;
}
.tr-side-sub {
  color: var(--muted);
  font-size: 0.85rem;
  margin: 0 0 1rem 0;
}
.tr-side-label {
  color: var(--muted);
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin: 0.85rem 0 0.35rem 0;
}
[data-testid="stSidebar"] .stButton > button {
  border-radius: 8px !important;
  justify-content: flex-start !important;
  text-align: left !important;
  font-weight: 500 !important;
  padding: 0.45rem 0.75rem !important;
}
[data-testid="stSidebar"] .stButton > button[kind="secondary"],
[data-testid="stSidebar"] div[data-testid="stButton"] button[data-testid="baseButton-secondary"] {
  background: transparent !important;
  border: 1px solid transparent !important;
  color: var(--ink) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
  background: var(--soft) !important;
  border-color: var(--line) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background: #e8ddd0 !important;
  border-color: #d9cbb8 !important;
  color: var(--ink) !important;
}

/* Empty chat home — Claude-like */
.tr-chat-home {
  text-align: center;
  padding: 4.5rem 1rem 1.5rem;
}
.tr-chat-home-title {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 1.75rem;
  font-weight: 500;
  color: var(--ink);
  margin: 0 0 0.4rem 0;
}
.tr-chat-home-sub {
  color: var(--muted);
  font-size: 1.05rem;
  margin: 0 0 1.6rem 0;
}

/* Сообщения и поле ввода */
[data-testid="stChatMessage"] {
  background: transparent !important;
  padding: 0.35rem 0 !important;
}
[data-testid="stChatMessage"] [data-testid="stChatMessageContent"] {
  background: var(--panel) !important;
  border: 1px solid var(--line) !important;
  border-radius: 14px !important;
  padding: 0.75rem 1rem !important;
}
[data-testid="stChatInput"] {
  background: var(--bg) !important;
}
[data-testid="stChatInput"] textarea {
  border-radius: 14px !important;
  border-color: var(--line) !important;
  background: #fff !important;
  font-size: 1rem !important;
}

.tr-desk-back {
  margin: 0 0 0.85rem 0;
}

/* Карточки Streamlit 1.4+ */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--panel) !important;
  border: 1px solid var(--line) !important;
  border-radius: 14px !important;
  box-shadow: 0 8px 22px rgba(139, 115, 85, 0.05) !important;
  padding: 0.15rem 0.2rem;
  margin: 0.55rem 0 0.9rem !important;
}

.tr-brand {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 1.55rem;
  color: var(--ink);
  margin: 0 0 0.15rem 0;
  font-weight: 500;
}
.tr-brand-sub {
  color: var(--muted);
  font-size: 0.95rem;
  margin: 0 0 1.1rem 0;
}

.tr-why {
  margin-top: 0.7rem;
  padding: 0.7rem 0.85rem;
  background: var(--soft);
  border-radius: 10px;
  border-left: 3px solid var(--accent);
  font-size: 0.9rem;
  line-height: 1.45;
  color: var(--muted);
}
.tr-why strong {
  color: var(--ink);
  font-weight: 600;
}

.tr-think {
  margin: 0 0 0.9rem 0;
  padding: 1rem 1.15rem 1.05rem;
  background: var(--soft);
  border-radius: 14px;
  border-left: 3px solid var(--accent);
  color: var(--muted);
  max-height: 18rem;
  overflow-y: auto;
}
.tr-think-kicker {
  font-family: "Source Sans 3", "Segoe UI", sans-serif;
  font-size: 0.68rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 0.55rem 0;
}
.tr-think-body, .tr-think > p {
  font-family: "Source Serif 4", Georgia, serif;
  font-style: italic;
  font-size: 1.02rem;
  line-height: 1.62;
  margin: 0;
  color: var(--ink);
}
@keyframes tr-breathe {
  0%, 100% { opacity: 0.45; }
  50% { opacity: 1; }
}
.tr-think-wait .tr-think-kicker {
  animation: tr-breathe 2.8s ease-in-out infinite;
}
.tr-think-hint {
  margin-top: 0.4rem;
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 0.95rem;
  font-style: italic;
  line-height: 1.5;
  color: var(--muted);
}
.tr-voice {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 1.35rem 1.4rem 1.2rem;
  margin: 0.9rem 0 1.3rem;
  box-shadow: 0 8px 22px rgba(139, 115, 85, 0.05);
}
.tr-voice-kicker {
  font-size: 0.68rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 0.35rem 0;
}
.tr-voice-title {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 1.45rem;
  font-weight: 500;
  color: var(--ink);
  margin: 0 0 0.85rem 0;
  letter-spacing: -0.02em;
}
.tr-voice-lead {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 1.08rem;
  line-height: 1.65;
  color: var(--ink);
  margin: 0 0 1rem 0;
}
.tr-voice-body {
  font-size: 0.95rem;
  line-height: 1.55;
  color: var(--muted);
  margin: 0 0 0.85rem 0;
}
.tr-voice-label {
  display: block;
  font-size: 0.68rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--accent);
  margin: 0 0 0.25rem 0;
}
.tr-voice-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.85rem 1.1rem;
  margin: 0.4rem 0 1rem;
}
@media (max-width: 640px) {
  .tr-voice-grid { grid-template-columns: 1fr; }
}
.tr-voice-shade {
  background: var(--soft);
  border-radius: 12px;
  padding: 0.75rem 0.85rem;
}
.tr-voice-shade-t {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 1.02rem;
  color: var(--ink);
  margin: 0 0 0.35rem 0;
}
.tr-voice-shade p {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.5;
  color: var(--muted);
}
.tr-voice-quote {
  margin: 0.45rem 0;
  padding: 0.15rem 0 0.15rem 0.9rem;
  border-left: 2px solid var(--accent);
  font-family: "Source Serif 4", Georgia, serif;
  font-style: italic;
  font-size: 1.02rem;
  line-height: 1.5;
  color: var(--ink);
}
.tr-voice-words, .tr-voice-not {
  font-size: 0.86rem;
  line-height: 1.5;
  color: var(--muted);
  margin: 0.7rem 0 0;
}
.tr-empty {
  padding: 2rem 1rem;
  text-align: center;
  color: var(--muted);
  font-size: 1.05rem;
  line-height: 1.65;
  font-family: "Source Serif 4", Georgia, serif;
  background: var(--panel);
  border: 1px dashed var(--line);
  border-radius: 14px;
  margin: 0.8rem 0 1.2rem;
}
.tr-empty-icon {
  display: block;
  font-size: 1.7rem;
  margin-bottom: 0.4rem;
  opacity: 0.45;
}
[data-testid="stFileUploaderDropzoneInstructions"] span {
  font-size: 0 !important;
}
[data-testid="stFileUploaderDropzoneInstructions"]::after {
  content: "перетащи кадр или выбери файл";
  font-size: 0.92rem !important;
  color: var(--muted);
  font-family: "Source Sans 3", "Segoe UI", sans-serif;
}
[data-testid="stFileUploader"] small {
  display: none !important;
}

.tr-chip {
  display: block;
  background: var(--soft);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 0.45rem 0.5rem;
  margin: 0.25rem 0;
  font-size: 0.82rem;
  line-height: 1.3;
  color: var(--ink);
  text-align: left;
}
.tr-day {
  font-family: "Source Serif 4", Georgia, serif;
  font-size: 0.8rem;
  color: var(--muted);
  text-align: center;
  margin-bottom: 0.35rem;
  padding-bottom: 0.25rem;
  border-bottom: 1px solid var(--line);
}

/* Кнопки: основные и тихие */
.stButton > button {
  background: var(--accent) !important;
  color: #faf8f5 !important;
  border: 1px solid var(--accent) !important;
  border-radius: 10px !important;
  padding: 0.38rem 0.9rem !important;
  font-weight: 500 !important;
  box-shadow: none !important;
}
.stButton > button:hover {
  background: var(--accent-hover) !important;
  border-color: var(--accent-hover) !important;
  color: #faf8f5 !important;
}
.stButton > button[kind="secondary"],
div[data-testid="stButton"] button[data-testid="baseButton-secondary"] {
  background: transparent !important;
  color: var(--accent) !important;
  border: 1px solid var(--line) !important;
}
.stButton > button[kind="secondary"]:hover,
div[data-testid="stButton"] button[data-testid="baseButton-secondary"]:hover {
  background: var(--soft) !important;
  border-color: var(--accent) !important;
  color: var(--accent-hover) !important;
}

div[data-testid="stMetric"] {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 0.55rem 0.7rem;
}
div[data-testid="stMetric"] label {
  color: var(--muted) !important;
}

textarea, input, [data-baseweb="input"], [data-baseweb="textarea"],
[data-baseweb="select"] > div {
  border-radius: 10px !important;
  border-color: var(--line) !important;
  background: #fff !important;
}

[data-testid="stExpander"] {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  margin: 0.4rem 0;
}
div[data-testid="stAlert"] {
  border-radius: 12px !important;
}

hr {
  border: none;
  border-top: 1px solid var(--line);
  margin: 1.1rem 0;
}
</style>
"""


def inject_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def brand_header(subtitle: str = "ассистент, не автор") -> None:
    st.markdown(
        f'<div class="tr-brand">Тихая редакция</div>'
        f'<p class="tr-brand-sub">{subtitle}</p>',
        unsafe_allow_html=True,
    )


def desk_back_to_chat() -> None:
    """Возврат со стола в диалог (Claude-like: инструменты вторичны)."""
    if st.button("← к диалогу", type="secondary", key="desk_back"):
        st.session_state["nav_to"] = "Чат"
        st.rerun()


def why_block(why: dict | None) -> None:
    if not why:
        return
    summary = (why.get("summary") or "").strip()
    season = (why.get("seasonality") or "").strip()
    related = why.get("related_posts") or []
    pattern = (why.get("audience_pattern") or "").strip()
    bits: list[str] = []
    if summary:
        bits.append(summary)
    if season:
        bits.append(season)
    if related:
        short = []
        for item in related[:2]:
            text = str(item).strip().strip("«»")
            if len(text) > 70:
                text = text[:67].rstrip() + "…"
            short.append(f"«{text}»")
        bits.append("из архива: " + "; ".join(short))
    if pattern:
        bits.append(pattern)
    if not bits:
        return
    st.markdown(
        f'<div class="tr-why"><strong>Почему</strong><br>{" · ".join(bits)}</div>',
        unsafe_allow_html=True,
    )


def archive_paste_widget(*, key: str, min_blocks: int = 2) -> None:
    """Вставка своих постов — на знакомстве и позже."""
    pasted = st.text_area(
        "Свои посты",
        placeholder="Пост 1:\n...\n\nПост 2:\n...",
        height=200,
        key=f"{key}_pasted",
    )
    if st.button("сохранить в память", key=f"{key}_save"):
        blocks = [b.strip() for b in pasted.split("\n\n") if b.strip()]
        if len(blocks) < min_blocks:
            st.warning(
                "Нужно хотя бы два блока — так я лучше чувствую голос."
                if min_blocks > 1
                else "Нужен хотя бы один пост."
            )
            return
        try:
            with st.spinner("сохраняю…"):
                api_post("/onboarding/archive", json={"posts": blocks})
            st.success("Тексты в памяти. Голос дособирается тихо 🤍")
            st.rerun()
        except Exception as exc:
            friendly_error(exc)


def archive_needed_banner() -> None:
    """Если архив пуст — сначала стена VK, вставка руками только запасной путь."""
    try:
        status = api_get("/onboarding/status")
    except Exception as exc:
        friendly_error(exc)
        return
    posts_n = int(status.get("posts_imported") or 0)
    if posts_n >= 2:
        return

    vk_ok = vk_is_configured()
    if vk_ok:
        empty_state(
            "В памяти ещё нет твоих постов. Загрузи со стены VK — так редакция узнает "
            "голос и сообщество. Вставка руками нужна только если стена недоступна."
        )
        if st.session_state.get("vk_wall_error"):
            st.error(st.session_state["vk_wall_error"])
        if st.button("загрузить посты со стены VK", key="dash_import_vk"):
            try:
                with st.spinner("читаю стену…"):
                    api_post("/onboarding/import-vk")
                st.session_state.pop("vk_wall_error", None)
                st.success("Посты в памяти. Голос дособирается тихо 🤍")
                st.rerun()
            except Exception as exc:
                from ui.api_client import ApiError

                msg = exc.message if isinstance(exc, ApiError) else str(exc)
                st.session_state["vk_wall_error"] = msg
                st.error(msg)
        with st.expander("Вставить тексты вручную", expanded=False):
            st.caption(
                "Если со стены не получается (ограничения доступа) — "
                "вставь 3–8 своих постов ниже."
            )
            archive_paste_widget(key="dash_archive", min_blocks=2)
        return

    empty_state(
        "Без твоих текстов я буду угадывать. Вставь 3–8 своих постов — "
        "про чай, стол, тихое утро — и редакция станет настоящей 🤍"
    )
    archive_paste_widget(key="dash_archive", min_blocks=2)


def feedback_buttons(suggestion_id: int | None, key_prefix: str) -> None:
    if not suggestion_id:
        return
    c1, c2, _ = st.columns([1.1, 1.4, 2.5])
    with c1:
        if st.button(
            "учту",
            key=f"{key_prefix}_yes_{suggestion_id}",
            help="Запомню этот выбор",
            type="secondary",
        ):
            try:
                api_post(f"/feedback/{suggestion_id}", json={"accepted": True, "note": ""})
                st.success("Учтено 🤍")
            except Exception as exc:
                friendly_error(exc)
    with c2:
        if st.button(
            "не соглашусь",
            key=f"{key_prefix}_no_{suggestion_id}",
            help="Не моё, запомню",
            type="secondary",
        ):
            try:
                api_post(f"/feedback/{suggestion_id}", json={"accepted": False, "note": ""})
                st.info("Запомнила — не моё")
            except Exception as exc:
                friendly_error(exc)


def _html(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\n", "<br>")
    )


_SHADE_TITLES = {
    "recipes": "Рецепты",
    "beauty": "Бьюти",
    "home": "Дом",
    "vlogs": "Влоги",
}


def voice_status_widget() -> None:
    """Портрет голоса — как страница журнала, не анкета."""
    try:
        voice = api_get("/voice")
    except Exception as exc:
        friendly_error(exc)
        return
    if not voice:
        try:
            status = api_get("/onboarding/status")
            posts_n = int(status.get("posts_imported") or 0)
        except Exception as exc:
            friendly_error(exc)
            return
        if posts_n < 2:
            return
        st.caption("Голос ещё собирается из архива — первые советы могут быть без оттенка.")
        return

    profile = voice.get("profile") or {}
    tone = str(profile.get("tone") or "").strip()
    address = str(profile.get("address") or "").strip()
    shades = profile.get("shades") or {}
    phrases = [str(p).strip() for p in (profile.get("sample_phrases") or []) if str(p).strip()]
    lexicon = [str(w).strip() for w in (profile.get("lexicon") or []) if str(w).strip()]
    forbidden = [str(w).strip() for w in (profile.get("forbidden_vibes") or []) if str(w).strip()]

    bits: list[str] = ['<div class="tr-voice">']
    bits.append('<p class="tr-voice-kicker">Голос</p>')
    bits.append('<p class="tr-voice-title">Как ты звучишь</p>')
    if tone:
        bits.append(f'<p class="tr-voice-lead">{_html(tone)}</p>')
    if address:
        bits.append(
            '<p class="tr-voice-body">'
            '<span class="tr-voice-label">К кому</span>'
            f"{_html(address)}</p>"
        )
    shade_cards = []
    for key, title in _SHADE_TITLES.items():
        text = str(shades.get(key) or "").strip()
        if not text:
            continue
        shade_cards.append(
            f'<div class="tr-voice-shade"><div class="tr-voice-shade-t">{title}</div>'
            f"<p>{_html(text)}</p></div>"
        )
    if shade_cards:
        bits.append('<div class="tr-voice-grid">' + "".join(shade_cards) + "</div>")
    for quote in phrases[:4]:
        q = quote if quote.startswith("«") else f"«{quote}»"
        bits.append(f'<blockquote class="tr-voice-quote">{_html(q)}</blockquote>')
    if lexicon:
        bits.append(
            '<p class="tr-voice-words">'
            + " · ".join(_html(w) for w in lexicon[:8])
            + "</p>"
        )
    if forbidden:
        bits.append(
            '<p class="tr-voice-not">Рядом с тобой не звучит: '
            + "; ".join(_html(w) for w in forbidden[:4])
            + "</p>"
        )
    bits.append("</div>")
    st.markdown("".join(bits), unsafe_allow_html=True)
    with st.expander("добавить тексты в архив", expanded=False):
        archive_paste_widget(key="voice_more", min_blocks=1)


def empty_state(text: str, icon: str | None = None) -> None:
    mark = f'<span class="tr-empty-icon">{icon}</span>' if icon else ""
    st.markdown(f'<div class="tr-empty">{mark}{text}</div>', unsafe_allow_html=True)

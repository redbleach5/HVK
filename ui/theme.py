"""Стили и общие виджеты интерфейса."""

from __future__ import annotations

import streamlit as st

from ui.api_client import api_post, friendly_error

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@500;600&display=swap');

:root {
  --ink: #14181c;
  --muted: #5c6570;
  --line: #d8dde3;
  --bg: #f3f4f6;
  --panel: #ffffff;
  --accent: #1f4d3a;
  --accent-hover: #16382b;
}

html, body, [class*="css"] {
  font-family: "IBM Plex Sans", system-ui, sans-serif;
  color: var(--ink);
}
.stApp {
  background: var(--bg);
}
h1, h2, h3 {
  font-family: "IBM Plex Serif", "IBM Plex Sans", serif !important;
  color: var(--ink) !important;
  font-weight: 600 !important;
  letter-spacing: -0.02em;
}
.block-container {
  padding-top: 1.5rem;
  padding-bottom: 2.5rem;
  max-width: 880px;
}
div[data-testid="stSidebar"] {
  background: #eceef1;
  border-right: 1px solid var(--line);
}
div[data-testid="stSidebar"] h2 {
  font-size: 1.15rem !important;
}
.tr-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 1rem 1.1rem;
  margin: 0.65rem 0;
}
.tr-why {
  margin-top: 0.65rem;
  padding: 0.7rem 0.85rem;
  background: #eef1f4;
  border-radius: 4px;
  border-left: 3px solid var(--accent);
  font-size: 0.9rem;
  color: var(--muted);
}
.tr-empty {
  padding: 1.5rem 0;
  color: var(--muted);
  font-size: 0.95rem;
}
.stButton > button {
  background: var(--accent);
  color: #f7f8f9;
  border: 1px solid var(--accent);
  border-radius: 6px;
  padding: 0.4rem 0.95rem;
  font-weight: 500;
}
.stButton > button:hover {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
  color: #f7f8f9;
}
textarea, input, [data-baseweb="input"], [data-baseweb="textarea"] {
  border-radius: 6px !important;
}
/* Убрать служебный хром Streamlit */
#MainMenu, header, footer,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
.stDeployButton,
div[data-testid="stAppDeployButton"] {
  display: none !important;
  visibility: hidden !important;
}
section.main > div:first-child {
  padding-top: 1rem;
}
</style>
"""


def inject_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def why_block(why: dict | None) -> None:
    if not why:
        return
    summary = why.get("summary") or ""
    season = why.get("seasonality") or ""
    related = why.get("related_posts") or []
    pattern = why.get("audience_pattern") or ""
    bits = [summary]
    if season:
        bits.append(season)
    if related:
        bits.append("Посты: " + "; ".join(related[:3]))
    if pattern:
        bits.append(pattern)
    st.markdown(
        f'<div class="tr-why"><strong>Основание</strong><br>{" · ".join(b for b in bits if b)}</div>',
        unsafe_allow_html=True,
    )


def feedback_buttons(suggestion_id: int | None, key_prefix: str) -> None:
    if not suggestion_id:
        return
    c1, c2, _ = st.columns([1, 1, 3])
    with c1:
        if st.button("принять", key=f"{key_prefix}_yes_{suggestion_id}"):
            try:
                api_post(f"/feedback/{suggestion_id}", json={"accepted": True, "note": ""})
                st.success("Сохранено")
            except Exception as exc:
                friendly_error(exc)
    with c2:
        if st.button("отклонить", key=f"{key_prefix}_no_{suggestion_id}"):
            try:
                api_post(f"/feedback/{suggestion_id}", json={"accepted": False, "note": ""})
                st.info("Отклонено")
            except Exception as exc:
                friendly_error(exc)


def empty_state(text: str) -> None:
    st.markdown(f'<div class="tr-empty">{text}</div>', unsafe_allow_html=True)


def card_start() -> None:
    st.markdown('<div class="tr-card">', unsafe_allow_html=True)


def card_end() -> None:
    st.markdown("</div>", unsafe_allow_html=True)

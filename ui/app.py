"""Streamlit-дашборд «Тихая редакция» — чат как основной интерфейс."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from ui.api_client import api_delete, api_get, api_post, friendly_error
from ui.chat_view import page_chat
from ui.theme import inject_theme

st.set_page_config(
    page_title="Тихая редакция",
    page_icon="✎",
    layout="centered",
    initial_sidebar_state="expanded",
)

inject_theme()


def run_onboarding() -> bool:
    """Мастер знакомства. True, если онбординг ещё не завершён."""
    try:
        status = api_get("/onboarding/status")
    except Exception as exc:
        friendly_error(exc)
        st.stop()

    if status.get("done"):
        return False

    st.title("Тихая редакция")
    st.markdown(
        '<p style="color:#5c6570;margin-top:-0.5rem;">Три шага. Токены и модели — в .env.</p>',
        unsafe_allow_html=True,
    )

    step = int(status.get("step") or 0)

    if step < 1:
        st.subheader("1. О блоге")
        name = st.text_input("Название", value=status.get("blog_name") or "Красивое в обычном")
        about = st.text_area(
            "Кратко о себе",
            value=status.get("about") or "",
            placeholder="Темы, тон, что обычно постишь",
        )
        if st.button("дальше"):
            try:
                api_post("/onboarding/profile", json={"blog_name": name, "about": about})
                st.rerun()
            except Exception as exc:
                friendly_error(exc)
        return True

    if step < 2:
        st.subheader("2. Голос и архив")
        st.write("Импорт постов из VK и профиль голоса. Нужен токен в .env.")
        st.caption(f"В архиве: {status.get('posts_imported', 0)} постов")
        if st.button("импортировать"):
            try:
                with st.spinner("Импорт…"):
                    api_post("/onboarding/import-vk")
                st.rerun()
            except Exception as exc:
                friendly_error(exc)
        if st.button("пропустить"):
            try:
                api_post("/onboarding/skip-import")
                st.rerun()
            except Exception as exc:
                friendly_error(exc)
        return True

    st.subheader("3. Готово")
    st.write(
        "Дальше всё через **чат**: сводка, идеи, фото, редактура, ЛС, план, аналитика, публикация."
    )
    if status.get("voice_ready"):
        st.success("Профиль голоса готов")
    else:
        st.info("Голос появится после импорта из VK")
    if st.button("открыть"):
        try:
            api_post("/onboarding/complete")
            st.rerun()
        except Exception as exc:
            friendly_error(exc)
    return True


def main() -> None:
    if run_onboarding():
        return

    st.sidebar.markdown("## Тихая редакция")
    st.sidebar.caption("чат · не автопостинг")

    try:
        health = api_get("/health")
        st.sidebar.caption(health.get("message") or "")
    except Exception:
        st.sidebar.caption("API недоступен")

    with st.sidebar.expander("Как пользоваться", expanded=False):
        st.markdown(
            "Пиши в чат как редактору.\n\n"
            "**сегодня** — сводка\n"
            "**идеи** / **план** / **аналитика**\n"
            "Фото — прикрепи файл\n"
            "Длинный текст — редактура\n"
            "**ответь на: …** — черновик ЛС\n"
            "**опубликовать: … подтверждаю** — пост в VK\n"
            "**в план: тема** — пункт плана\n\n"
            "принять / отклонить под карточками — обучение."
        )

    if st.sidebar.button("очистить чат"):
        try:
            api_delete("/chat/history")
            st.session_state["chat_messages"] = []
            st.session_state.pop("chat_loaded", None)
            st.rerun()
        except Exception as exc:
            friendly_error(exc)

    page_chat()


if __name__ == "__main__":
    main()

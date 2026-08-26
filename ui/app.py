"""Streamlit shell «Тихая редакция» — диалог в центре, стол слева (Claude-like)."""

from __future__ import annotations

import sys
from pathlib import Path

_UI_DIR = Path(__file__).resolve().parent
_ROOT = _UI_DIR.parent
# Streamlit кладёт каталог скрипта (ui/) в sys.path — тогда `import app`
# берёт ui/app.py вместо пакета app/. Убираем тень.
sys.path[:] = [p for p in sys.path if Path(p).resolve() != _UI_DIR]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st

from ui.api_client import api_get, api_post, friendly_error, vk_is_configured
from ui.chat_view import page_chat
from ui.desk import load_desk, save_desk
from ui.pages_view import (
    page_analytics,
    page_concierge,
    page_ideas,
    page_photo,
    page_text,
    page_today,
)
from ui.theme import (
    archive_needed_banner,
    archive_paste_widget,
    desk_back_to_chat,
    inject_theme,
)

NAV_CHAT = "Чат"
NAV_DESK = ["Сегодня", "Фото", "Текст", "Идеи и план", "Аналитика"]

st.set_page_config(
    page_title="Тихая редакция",
    page_icon="🤍",
    layout="centered",
    initial_sidebar_state="expanded",
)

inject_theme()


def _go_nav(name: str) -> None:
    st.session_state["main_nav"] = name
    save_desk()
    st.rerun()


def _hydrate_desk(items: list[str]) -> None:
    if st.session_state.get("_desk_ready"):
        return
    try:
        data = load_desk()
    except Exception as exc:
        friendly_error(exc)
        data = {}
    nav = data.get("desk") or NAV_CHAT
    st.session_state["main_nav"] = nav if nav in items else NAV_CHAT
    if "current_draft" not in st.session_state:
        st.session_state["current_draft"] = str(data.get("draft_text") or "")
    if "plan_item_id" not in st.session_state and data.get("plan_item_id") is not None:
        st.session_state["plan_item_id"] = data["plan_item_id"]
    st.session_state["_desk_ready"] = True


def _nav_items() -> list[str]:
    items = [NAV_CHAT, *NAV_DESK]
    if vk_is_configured():
        items.append("ЛС")
    return items


def _sidebar_nav(items: list[str]) -> None:
    st.sidebar.markdown(
        '<div class="tr-side-brand">Тихая редакция</div>'
        '<p class="tr-side-sub">ассистент, не автор</p>',
        unsafe_allow_html=True,
    )
    if st.session_state.get("main_nav") not in items:
        st.session_state["main_nav"] = NAV_CHAT

    st.sidebar.markdown('<p class="tr-side-label">Диалог</p>', unsafe_allow_html=True)
    if st.sidebar.button(
        "Чат",
        key="nav_chat",
        use_container_width=True,
        type="primary" if st.session_state["main_nav"] == NAV_CHAT else "secondary",
    ):
        _go_nav(NAV_CHAT)

    st.sidebar.markdown('<p class="tr-side-label">Стол</p>', unsafe_allow_html=True)
    for name in items:
        if name == NAV_CHAT:
            continue
        active = st.session_state["main_nav"] == name
        if st.sidebar.button(
            name,
            key=f"nav_{name}",
            use_container_width=True,
            type="primary" if active else "secondary",
        ):
            _go_nav(name)

    try:
        voice = api_get("/voice")
        caption = "голос собран" if voice else "голос появится с архивом"
    except Exception:
        caption = ""
    if caption:
        st.sidebar.caption(caption)


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
        '<p style="color:#7a6a5c;margin-top:-0.5rem;">'
        "Три шага. Потом — диалог, как привычный чат. Стол слева, без настроек."
        "</p>",
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
        st.subheader("2. Покажи свой голос")
        st.write(
            "Нужны твои посты в памяти — так я узнаю голос и сообщество. "
            "Если VK подключён, сначала загрузи со стены; вставка руками — запасной путь."
        )

        vk_ok = vk_is_configured()

        if vk_ok:
            st.caption(f"В архиве: {status.get('posts_imported', 0)} постов")
            if st.button("загрузить посты со стены VK"):
                try:
                    with st.spinner("читаю стену…"):
                        api_post("/onboarding/import-vk")
                    st.rerun()
                except Exception as exc:
                    friendly_error(exc)
            with st.expander("Или вставить тексты вручную", expanded=True):
                archive_paste_widget(key="onb_step2", min_blocks=2)
        else:
            st.write(
                "VK пока не подключён — вставь 3–8 своих постов "
                "(про чай, стол, тихое утро — что угодно живое)."
            )
            archive_paste_widget(key="onb_step2", min_blocks=2)

        return True

    st.subheader("3. Готово")
    st.write("Дальше — диалог. Слева тихий стол, когда нужен экран:")
    st.markdown(
        "- **Чат** — главный экран: спроси «сегодня», «идеи», пришли фото\n"
        "- **Сегодня** — сводка за день\n"
        "- **Фото / Текст** — разбор кадра и правки по одной\n"
        "- **Идеи и план** — сезон и неделя\n"
        "- **Аналитика** — что заходило"
    )

    if status.get("voice_ready"):
        st.success("🤍 Голос собран — идеи и редактура будут опираться на твои тексты")
    elif int(status.get("posts_imported") or 0) > 0:
        st.info(
            f"Тексты уже в памяти ({status['posts_imported']} постов). "
            "Голос дособирается — можно открывать, но первые идеи могут быть без голоса."
        )
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("обновить статус"):
                st.rerun()
        with col_b:
            if st.button("собрать голос ещё раз"):
                try:
                    api_post("/onboarding/rebuild-voice")
                    st.rerun()
                except Exception as exc:
                    friendly_error(exc)
    else:
        st.info(
            "Архив пуст. Без твоих текстов я буду угадывать — "
            "вставь 3–8 постов сейчас, и всё станет настоящим 🤍"
        )
        archive_paste_widget(key="onb_step3", min_blocks=2)

    posts_n = int(status.get("posts_imported") or 0)
    if posts_n < 2:
        st.caption("Открою диалог, когда в памяти будут хотя бы два твоих поста.")
        return True

    if st.button("открыть"):
        try:
            api_post("/onboarding/complete")
            st.session_state["main_nav"] = NAV_CHAT
            st.rerun()
        except Exception as exc:
            friendly_error(exc)
    return True


def main() -> None:
    if run_onboarding():
        return

    items = _nav_items()
    _hydrate_desk(items)
    if "nav_to" in st.session_state:
        target = st.session_state.pop("nav_to")
        if target in items:
            st.session_state["main_nav"] = target
            save_desk()
    if st.session_state.get("main_nav") not in items:
        st.session_state["main_nav"] = NAV_CHAT

    _sidebar_nav(items)

    page = st.session_state["main_nav"]
    if page == NAV_CHAT:
        page_chat()
        return

    archive_needed_banner()
    desk_back_to_chat()
    if page == "Сегодня":
        page_today()
    elif page == "Фото":
        page_photo()
    elif page == "Текст":
        page_text()
    elif page == "Идеи и план":
        page_ideas()
    elif page == "Аналитика":
        page_analytics()
    elif page == "ЛС":
        page_concierge()


if __name__ == "__main__":
    main()

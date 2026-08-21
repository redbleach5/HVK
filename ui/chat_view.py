"""Чат-интерфейс: основной способ работы с редакцией."""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.api_client import api_delete, api_get, api_post, api_post_form, friendly_error
from ui.theme import feedback_buttons


def _ensure_history() -> None:
    if "chat_loaded" in st.session_state:
        return
    try:
        data = api_get("/chat/history")
        st.session_state["chat_messages"] = data.get("messages") or []
    except Exception:
        st.session_state["chat_messages"] = []
    st.session_state["chat_loaded"] = True


def _render_card(card: dict[str, Any], key_prefix: str) -> None:
    ctype = card.get("type") or ""
    title = card.get("title") or ""
    body = card.get("body") or ""
    data = card.get("data") or {}
    sid = card.get("suggestion_id")

    with st.container(border=True):
        if title:
            st.markdown(f"**{title}**")
        if body:
            st.write(body)

        if ctype == "idea":
            meta = []
            if data.get("format"):
                meta.append(str(data["format"]))
            if data.get("effort"):
                meta.append(f"усилие: {data['effort']}")
            if data.get("why_now"):
                meta.append(str(data["why_now"]))
            if meta:
                st.caption(" · ".join(meta))
            idea_id = data.get("id")
            if idea_id and st.button("в план", key=f"{key_prefix}_plan_{idea_id}"):
                try:
                    out = api_post(f"/chat/idea/{idea_id}/to-plan")
                    st.session_state.setdefault("chat_messages", []).append(
                        {
                            "role": "assistant",
                            "content": out.get("reply") or "В плане.",
                            "cards": out.get("cards") or [],
                            "suggestion_ids": out.get("suggestion_ids") or [],
                        }
                    )
                    st.rerun()
                except Exception as exc:
                    friendly_error(exc)
            if data.get("personal_angle") or data.get("description"):
                if st.button("в черновик чата", key=f"{key_prefix}_draft_{idea_id or title}"):
                    st.session_state["chat_prefill"] = (
                        f"{title}\n\n{data.get('personal_angle') or ''}\n\n"
                        f"{data.get('description') or body}"
                    ).strip()
                    st.rerun()

        elif ctype == "edit":
            if data.get("openings"):
                st.caption("Другие первые строки")
                for line in data["openings"][:4]:
                    st.markdown(f"· {line}")
            revised = data.get("revised_text") or body
            if revised and st.button(
                "опубликовать (нужно подтверждение в чате)",
                key=f"{key_prefix}_pub_hint",
            ):
                st.session_state["chat_prefill"] = (
                    f"опубликовать: {revised}\n\nподтверждаю"
                )
                st.info("Отправь сообщение из поля ввода — или отредактируй перед отправкой.")
                st.rerun()

        elif ctype == "photo":
            scores = data.get("scores") or {}
            if scores:
                cols = st.columns(min(3, len(scores)))
                for i, (k, v) in enumerate(scores.items()):
                    cols[i % 3].metric(k, v)
            if data.get("caption_direction") and st.button(
                "подпись в чат", key=f"{key_prefix}_cap"
            ):
                st.session_state["chat_prefill"] = str(data["caption_direction"])
                st.rerun()

        elif ctype == "concierge":
            st.caption("Отправь сама в VK — система ничего не шлёт.")

        elif ctype == "inbox":
            preview = body
            if preview and st.button("ответить на это", key=f"{key_prefix}_inbox"):
                st.session_state["chat_prefill"] = f"ответь на: {preview}"
                st.rerun()

        elif ctype == "archive":
            if st.button("в план", key=f"{key_prefix}_arch_plan"):
                try:
                    item = api_post(
                        "/plan/from-text",
                        json={"title": (title or "Из архива")[:240], "draft_text": body},
                    )
                    st.success(f"В плане (id {item.get('id')})")
                except Exception as exc:
                    friendly_error(exc)

        if sid:
            feedback_buttons(sid, key_prefix)


def _send(message: str, files: list | None = None) -> None:
    data = {"message": message}
    form_files = None
    if files:
        form_files = [
            ("files", (f.name, f.getvalue(), f.type or "image/jpeg")) for f in files
        ]
    try:
        with st.spinner("…"):
            out = api_post_form("/chat", data=data, files=form_files)
    except Exception as exc:
        friendly_error(exc)
        return

    msgs = st.session_state.setdefault("chat_messages", [])
    user_content = message.strip() or ("[фото]" if files else "")
    msgs.append({"role": "user", "content": user_content, "cards": [], "suggestion_ids": []})
    msgs.append(
        {
            "role": "assistant",
            "content": out.get("reply") or "",
            "cards": out.get("cards") or [],
            "suggestion_ids": out.get("suggestion_ids") or [],
        }
    )


def page_chat() -> None:
    st.header("Чат")
    st.caption("Все возможности редакции — через диалог")

    _ensure_history()

    quick = st.columns(5)
    shortcuts = [
        ("сегодня", "сегодня"),
        ("идеи", "идеи"),
        ("план", "план"),
        ("аналитика", "аналитика"),
        ("помощь", "помощь"),
    ]
    for col, (label, text) in zip(quick, shortcuts):
        with col:
            if st.button(label, key=f"q_{label}"):
                _send(text)
                st.rerun()

    uploads = st.file_uploader(
        "Фото к сообщению",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key="chat_uploads",
    )

    for i, msg in enumerate(st.session_state.get("chat_messages") or []):
        role = msg.get("role") or "assistant"
        with st.chat_message(role):
            st.write(msg.get("content") or "")
            for j, card in enumerate(msg.get("cards") or []):
                if isinstance(card, dict):
                    _render_card(card, f"m{i}_c{j}")

    prefill = st.session_state.pop("chat_prefill", None)
    prompt = st.chat_input("Сообщение…")
    if prefill and not prompt:
        # показать как подсказку в info — chat_input нельзя программно заполнить стабильно
        st.session_state["chat_prefill_pending"] = prefill
    pending = st.session_state.pop("chat_prefill_pending", None)
    if pending:
        st.info(f"Черновик для отправки:\n\n{pending[:500]}")
        if st.button("отправить этот черновик"):
            _send(pending, files=list(uploads) if uploads else None)
            st.rerun()

    if prompt:
        _send(prompt, files=list(uploads) if uploads else None)
        st.rerun()

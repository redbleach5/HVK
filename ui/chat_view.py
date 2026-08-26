"""Чат-интерфейс: дом редакции в духе Claude."""

from __future__ import annotations

import time
from typing import Any

import streamlit as st

from ui.api_client import api_get, api_post, api_post_form, friendly_error, iter_chat_stream
from ui.theme import archive_needed_banner, feedback_buttons


def _ensure_history() -> None:
    if st.session_state.get("_chat_sending"):
        return
    try:
        data = api_get("/chat/history")
        st.session_state["chat_messages"] = data.get("messages") or []
    except Exception as exc:
        friendly_error(exc)
        st.session_state.setdefault("chat_messages", [])


def _render_card(card: dict[str, Any], key_prefix: str, *, thinking_open: bool = False) -> None:
    ctype = card.get("type") or ""
    title = card.get("title") or ""
    body = card.get("body") or ""
    data = card.get("data") or {}
    sid = card.get("suggestion_id")

    if ctype == "thinking":
        body_html = _esc(body or "")
        think_html = (
            f'<div class="tr-think">'
            f'<p class="tr-think-kicker">размышляю</p>'
            f'<p class="tr-think-body">{body_html}</p>'
            f"</div>"
        )
        if thinking_open:
            st.markdown(think_html, unsafe_allow_html=True)
        else:
            with st.expander("размышляю", expanded=False):
                st.markdown(
                    f'<div class="tr-think"><p class="tr-think-body">{body_html}</p></div>',
                    unsafe_allow_html=True,
                )
        return

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

        elif ctype == "why":
            plan_title = (data.get("plan_title") or title or "").strip()
            if plan_title and st.button("в план", key=f"{key_prefix}_why_plan"):
                try:
                    api_post(
                        "/plan/from-text",
                        json={"title": plan_title[:240], "draft_text": ""},
                    )
                    st.success("В плане")
                    st.rerun()
                except Exception as exc:
                    friendly_error(exc)

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


def _send(message: str, files: list | None = None) -> bool:
    st.session_state["_chat_sending"] = True
    try:
        if files:
            return _send_plain(message, files)
        return _send_stream(message)
    finally:
        st.session_state["_chat_sending"] = False


def _send_plain(message: str, files: list | None = None) -> bool:
    data = {"message": message}
    form_files = None
    if files:
        form_files = [
            ("files", (f.name, f.getvalue(), f.type or "image/jpeg")) for f in files
        ]
    try:
        with st.spinner("смотрю…"):
            out = api_post_form("/chat", data=data, files=form_files)
    except Exception as exc:
        msgs = st.session_state.setdefault("chat_messages", [])
        user_content = message.strip() or ("[фото]" if files else "")
        msgs.append({"role": "user", "content": user_content, "cards": [], "suggestion_ids": []})
        msgs.append(
            {
                "role": "assistant",
                "content": _error_text(exc),
                "cards": [],
                "suggestion_ids": [],
            }
        )
        return False

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
    return True


def _send_stream(message: str) -> bool:
    user_content = message.strip()
    msgs = st.session_state.setdefault("chat_messages", [])
    msgs.append({"role": "user", "content": user_content, "cards": [], "suggestion_ids": []})
    thinking = ""
    reply = ""
    cards: list = []
    sids: list = []
    last_paint = 0.0

    def _paint_think(*, force: bool = False) -> None:
        nonlocal last_paint
        now = time.monotonic()
        if not force and now - last_paint < 0.08:
            return
        last_paint = now
        if thinking:
            inner = (
                f'<p class="tr-think-kicker">размышляю</p>'
                f'<p class="tr-think-body">{_esc(thinking)}</p>'
            )
            cls = "tr-think"
        else:
            inner = (
                '<p class="tr-think-kicker">размышляю</p>'
                '<div class="tr-think-hint">собираю мысль — можно не торопиться</div>'
            )
            cls = "tr-think tr-think-wait"
        think_ph.markdown(f'<div class="{cls}">{inner}</div>', unsafe_allow_html=True)

    try:
        with st.chat_message("user"):
            st.write(user_content)
        with st.chat_message("assistant"):
            think_ph = st.empty()
            text_ph = st.empty()
            _paint_think(force=True)
            for ev in iter_chat_stream(message):
                kind = ev.get("t")
                if kind == "thinking":
                    thinking += ev.get("d") or ""
                    _paint_think()
                elif kind == "text":
                    if thinking:
                        _paint_think(force=True)
                    reply += ev.get("d") or ""
                    text_ph.markdown(reply)
                elif kind == "done":
                    reply = ev.get("reply") or reply
                    cards = ev.get("cards") or []
                    sids = ev.get("suggestion_ids") or []
                    if thinking:
                        _paint_think(force=True)
                    else:
                        think_ph.empty()
                    if reply:
                        text_ph.markdown(reply)
    except Exception as exc:
        msgs.append(
            {
                "role": "assistant",
                "content": _error_text(exc),
                "cards": [],
                "suggestion_ids": [],
            }
        )
        return False
    thought_cards = [c for c in cards if isinstance(c, dict)]
    msgs.append(
        {
            "role": "assistant",
            "content": reply,
            "cards": thought_cards,
            "suggestion_ids": sids,
        }
    )
    return True


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br>")
    )


def _error_text(exc: Exception) -> str:
    import httpx

    from ui.api_client import ApiError

    if isinstance(exc, ApiError):
        return exc.message
    if isinstance(exc, httpx.TimeoutException):
        return "Пока я думала, связь оборвалась. Напиши ещё раз — я на месте."
    return "Не получилось ответить. Напиши ещё раз."


def _empty_home() -> None:
    # Архив пуст — CTA здесь, в центре экрана, а не только полоской сверху
    archive_needed_banner()
    st.markdown(
        '<div class="tr-chat-home">'
        '<div class="tr-chat-home-title">Тихая редакция</div>'
        '<p class="tr-chat-home-sub">Чем помочь сегодня?</p>'
        "</div>",
        unsafe_allow_html=True,
    )
    chips = [
        ("Что сегодня?", "сегодня"),
        ("Идеи на неделю", "идеи"),
        ("Посмотри план", "план"),
        ("Помоги с текстом", "хочу поправить текст"),
    ]
    cols = st.columns(len(chips))
    for col, (label, text) in zip(cols, chips):
        with col:
            if st.button(label, key=f"chip_{text}", type="secondary", use_container_width=True):
                _send(text)
                st.rerun()


def page_chat() -> None:
    _ensure_history()
    msgs = st.session_state.get("chat_messages") or []

    if not msgs:
        _empty_home()
    else:
        # Если диалог уже есть, а архива нет — всё равно показать загрузку сверху
        archive_needed_banner()
        for i, msg in enumerate(msgs):
            role = msg.get("role") or "assistant"
            with st.chat_message(role):
                cards = [c for c in (msg.get("cards") or []) if isinstance(c, dict)]
                thoughts = [c for c in cards if c.get("type") == "thinking"]
                rest = [c for c in cards if c.get("type") != "thinking"]
                last_assistant = role == "assistant" and i == len(msgs) - 1
                for j, card in enumerate(thoughts):
                    _render_card(
                        card,
                        f"m{i}_t{j}",
                        thinking_open=last_assistant,
                    )
                if msg.get("content"):
                    st.write(msg.get("content") or "")
                for j, card in enumerate(rest):
                    _render_card(card, f"m{i}_c{j}")

    with st.expander("Прикрепить фото", expanded=False):
        uploads = st.file_uploader(
            "Фото к сообщению",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key="chat_uploads",
            label_visibility="collapsed",
        )

    uploads = st.session_state.get("chat_uploads") or []

    prefill = st.session_state.pop("chat_prefill", None)
    prompt = st.chat_input("Напиши сообщение…")
    if prefill and not prompt:
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

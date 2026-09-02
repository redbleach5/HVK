"""Чат-интерфейс: дом редакции в духе Claude."""

from __future__ import annotations

import re
import time
from typing import Any

import streamlit as st

from ui.api_client import api_delete, api_get, api_post, api_post_form, friendly_error, iter_chat_stream
from ui.desk import save_desk
from ui.theme import archive_needed_banner, copy_to_clipboard_button, feedback_buttons, toast


def _ensure_history() -> None:
    # После сбоя не перетираем локальный пузырь ошибки свежей историей с API.
    if st.session_state.pop("_chat_keep_local", None):
        return
    try:
        data = api_get("/chat/history")
        st.session_state["chat_messages"] = data.get("messages") or []
    except Exception as exc:
        friendly_error(exc)
        st.session_state.setdefault("chat_messages", [])


def _remember_plan(item_id: object) -> None:
    if item_id is None:
        return
    st.session_state["plan_item_id"] = item_id
    save_desk()


def _remember_draft(text: str) -> None:
    body = (text or "").strip()
    if not body:
        return
    st.session_state["current_draft"] = body
    save_desk()


def _render_card(
    card: dict[str, Any],
    key_prefix: str,
    *,
    thinking_open: bool = False,
    interactive: bool = True,
) -> None:
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

    if ctype == "why":
        short = re.sub(r"\s+", " ", (body or "").strip())
        if len(short) > 160:
            short = short[:157].rstrip() + "…"
        label = (title or "из твоих текстов").strip()
        line = " · ".join(x for x in (label, short) if x)
        st.markdown(
            f'<div class="tr-why">{_esc(line)}</div>',
            unsafe_allow_html=True,
        )
        plan_title = (data.get("plan_title") or "").strip()
        if interactive and plan_title and st.button("в план", key=f"{key_prefix}_why_plan"):
            try:
                item = api_post(
                    "/plan/from-text",
                    json={"title": plan_title[:240], "draft_text": ""},
                )
                _remember_plan(item.get("id"))
                st.session_state["_toast"] = "В плане"
                st.rerun()
            except Exception as exc:
                friendly_error(exc)
        if interactive and sid:
            feedback_buttons(sid, key_prefix)
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
                    item = api_post(f"/ideas/{idea_id}/to-plan")
                    _remember_plan(item.get("id"))
                    st.session_state.setdefault("chat_messages", []).append(
                        {
                            "role": "assistant",
                            "content": f"«{title or item.get('title') or 'идея'}» в плане.",
                            "cards": [],
                            "suggestion_ids": [],
                        }
                    )
                    st.session_state["_toast"] = "В плане"
                    st.rerun()
                except Exception as exc:
                    friendly_error(exc)
            if data.get("personal_angle") or data.get("description"):
                if st.button("в черновик", key=f"{key_prefix}_draft_{idea_id or title}"):
                    _remember_draft(
                        f"{title}\n\n{data.get('personal_angle') or ''}\n\n"
                        f"{data.get('description') or body}"
                    )
                    st.session_state["_toast"] = "В черновике"
                    st.rerun()

        elif ctype == "edit":
            if data.get("openings"):
                st.caption("Другие первые строки")
                for line in data["openings"][:4]:
                    st.markdown(f"· {line}")
            revised = data.get("revised_text") or body
            if revised:
                col_p, col_d = st.columns([2, 1])
                with col_p:
                    if st.button(
                        "опубликовать",
                        key=f"{key_prefix}_pub_hint",
                        help="Открою черновик для подтверждения в поле ввода",
                    ):
                        st.session_state["chat_prefill"] = (
                            f"опубликовать: {revised}\n\nподтверждаю"
                        )
                        st.rerun()
                with col_d:
                    copy_to_clipboard_button(revised, key=f"{key_prefix}_copy", label="копировать")

        elif ctype == "photo":
            scores = data.get("scores") or {}
            if scores:
                cols = st.columns(min(3, len(scores)))
                for i, (k, v) in enumerate(scores.items()):
                    cols[i % 3].metric(k, v)
            if data.get("caption_direction") and st.button(
                "в черновик", key=f"{key_prefix}_cap"
            ):
                _remember_draft(str(data["caption_direction"]))
                st.session_state["_toast"] = "В черновике"
                st.rerun()

        elif ctype == "concierge":
            st.caption("Отправь сама в VK — система ничего не шлёт.")
            if data.get("draft_reply"):
                copy_to_clipboard_button(
                    str(data["draft_reply"]), key=f"{key_prefix}_conc_copy"
                )

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
                    _remember_plan(item.get("id"))
                    st.session_state["_toast"] = "В плане"
                    st.rerun()
                except Exception as exc:
                    friendly_error(exc)

        if interactive and sid:
            feedback_buttons(sid, key_prefix)


def _finish_send(ok: bool, *, uploads_epoch: int | None = None) -> None:
    if ok and uploads_epoch is not None:
        st.session_state["chat_upload_epoch"] = uploads_epoch + 1
    if not ok:
        st.session_state["_chat_keep_local"] = True
    st.rerun()


def _send(message: str, files: list | None = None) -> bool:
    if files:
        return _send_plain(message, files)
    return _send_stream(message)


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
        # В живом UI показываем ошибку в bubble ассистента — не теряем её
        err_text = _error_text(exc)
        try:
            think_ph.empty()
            text_ph.markdown(f"_{err_text}_")
        except Exception:
            pass
        msgs.append(
            {
                "role": "assistant",
                "content": err_text,
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
        ("Что сегодня?", "сегодня", "chip_today"),
        ("Идеи", "идеи", "chip_ideas"),
        ("Что заходило?", "что лучше заходило в последнее время — и почему", "chip_hits"),
        ("Помоги с текстом", "хочу поправить текст", "chip_text"),
    ]
    cols = st.columns(len(chips))
    for col, (label, text, key) in zip(cols, chips):
        with col:
            if st.button(label, key=key, type="secondary", use_container_width=True):
                _finish_send(_send(text))


def _chat_header_actions() -> None:
    """Тихая строка действий над чатом: очистить диалог, вернуть в примеры."""
    msgs = st.session_state.get("chat_messages") or []
    if not msgs:
        return
    col_t, col_c = st.columns([5, 1])
    with col_c:
        if st.button("очистить", key="chat_clear", type="secondary", use_container_width=True,
                     help="Стереть диалог из памяти редакции"):
            try:
                api_delete("/chat/history")
                st.session_state["chat_messages"] = []
                st.session_state["_toast"] = "Диалог очищен"
                st.rerun()
            except Exception as exc:
                friendly_error(exc)


def _render_uploads_preview(uploads: list) -> None:
    """Превью прикреплённых фото над полем ввода — адаптивная сетка."""
    if not uploads:
        return
    n = min(len(uploads), 8)
    cols = st.columns(n)
    for i, up in enumerate(uploads[:n]):
        with cols[i]:
            st.image(up, use_container_width=True)


def page_chat() -> None:
    _ensure_history()
    msgs = st.session_state.get("chat_messages") or []

    # Тост (если он есть в session — показать один раз)
    _toast_pending = st.session_state.pop("_toast", None)
    if _toast_pending:
        toast(_toast_pending)

    if not msgs:
        _empty_home()
    else:
        # Если диалог уже есть, а архива нет — всё равно показать загрузку сверху
        archive_needed_banner()
        _chat_header_actions()
        last_assistant = -1
        for idx, m in enumerate(msgs):
            if m.get("role") == "assistant":
                last_assistant = idx
        for i, msg in enumerate(msgs):
            role = msg.get("role") or "assistant"
            interactive = role == "assistant" and i == last_assistant
            with st.chat_message(role):
                cards = [c for c in (msg.get("cards") or []) if isinstance(c, dict)]
                rest = [c for c in cards if c.get("type") != "thinking"]
                if msg.get("content"):
                    st.write(msg.get("content") or "")
                covered_sids: set[int] = set()
                for card in rest:
                    sid = card.get("suggestion_id")
                    if sid:
                        covered_sids.add(int(sid))
                for j, card in enumerate(rest):
                    _render_card(card, f"m{i}_c{j}", interactive=interactive)
                if interactive:
                    for k, sid in enumerate(msg.get("suggestion_ids") or []):
                        if not sid:
                            continue
                        sid_int = int(sid)
                        if sid_int in covered_sids:
                            continue
                        st.markdown('<div class="tr-chat-foot"></div>', unsafe_allow_html=True)
                        feedback_buttons(sid_int, f"m{i}_fb{k}")

    # Фото-аплоадер и pending — НАД полем ввода, чтобы пользователь видел
    uploads_epoch = int(st.session_state.get("chat_upload_epoch") or 0)
    uploads_key = f"chat_uploads_{uploads_epoch}"
    uploads_state = st.session_state.get(uploads_key) or []
    pending = st.session_state.pop("chat_prefill_pending", None)
    prefill = st.session_state.pop("chat_prefill", None)
    if prefill:
        st.session_state["chat_prefill_pending"] = prefill
        pending = prefill

    if pending:
        st.markdown(
            f'<div class="tr-pending">'
            f'<p class="tr-pending-kicker">черновик для отправки</p>'
            f'<div class="tr-pending-body">{_esc(pending[:1200])}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        col_send, col_cancel = st.columns(2)
        with col_send:
            if st.button("отправить", key="pending_send", type="primary", use_container_width=True):
                ok = _send(pending, files=list(uploads_state) if uploads_state else None)
                st.session_state.pop("chat_prefill_pending", None)
                _finish_send(ok, uploads_epoch=uploads_epoch)
        with col_cancel:
            if st.button("отмена", key="pending_cancel", use_container_width=True):
                st.session_state.pop("chat_prefill_pending", None)
                st.rerun()

    with st.expander("Прикрепить фото", expanded=bool(uploads_state)):
        st.file_uploader(
            "Фото к сообщению",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            key=uploads_key,
            label_visibility="collapsed",
        )
        if uploads_state:
            _render_uploads_preview(list(uploads_state))
            if st.button("убрать все фото", key="chat_clear_uploads", type="secondary"):
                st.session_state["chat_upload_epoch"] = uploads_epoch + 1
                st.rerun()

    prompt = st.chat_input("Напиши сообщение…")
    if prompt:
        ok = _send(prompt, files=list(uploads_state) if uploads_state else None)
        _finish_send(ok, uploads_epoch=uploads_epoch)

"""Страницы дашборда Streamlit."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import plotly.express as px
import streamlit as st

from ui.api_client import api_get, api_patch, api_post, api_post_form, friendly_error
from ui.theme import card_end, card_start, empty_state, feedback_buttons, why_block

_WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
_STATUS_LABEL = {
    "conceived": "задумано",
    "written": "написано",
    "published": "опубликовано",
}


def page_today() -> None:
    st.header("Сегодня")
    st.caption("Сводка, идеи и план")
    try:
        data = api_get("/today")
    except Exception as exc:
        friendly_error(exc)
        return

    card_start()
    st.markdown(data.get("digest") or "Сводки пока нет.")
    for h in data.get("highlights") or []:
        text = h.get("text") if isinstance(h, dict) else str(h)
        st.markdown(f"· {text}")
    why_block(data.get("why"))
    card_end()

    ideas = data.get("ideas") or []
    if ideas:
        st.subheader("Идеи")
        for i, idea in enumerate(ideas):
            with st.container():
                st.markdown(f"**{idea.get('theme')}** · {idea.get('format') or 'формат свободный'}")
                st.write(idea.get("description") or "")
                st.caption(idea.get("why_now") or "")
                why_block(idea.get("why"))
                feedback_buttons(idea.get("suggestion_id"), f"today_idea_{i}")
                if idea.get("id") and st.button("в план", key=f"today_plan_{idea['id']}"):
                    try:
                        api_post(f"/ideas/{idea['id']}/to-plan")
                        st.session_state["active_idea"] = idea
                        st.success("В плане")
                    except Exception as exc:
                        friendly_error(exc)
    else:
        empty_state("Идей нет. Открой «Идеи и план» или дождись сводки.")

    reminders = data.get("plan_reminders") or []
    if reminders:
        st.subheader("План")
        for line in reminders:
            st.markdown(f"· {line}")

    activity = data.get("activity") or []
    if activity:
        with st.expander("Недавние действия"):
            for a in activity:
                st.caption(f"{a.get('created_at', '')[:16]} — {a.get('summary')}")


def page_photo() -> None:
    st.header("Фото")
    st.caption("Разбор кадра или серии")
    uploads = st.file_uploader(
        "Фото",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    if not uploads:
        empty_state("Загрузи фото.")
        return
    if st.button("разобрать"):
        files = []
        for up in uploads:
            files.append(("files", (up.name, up.getvalue(), up.type or "image/jpeg")))
        try:
            with st.spinner("Анализ…"):
                result = api_post("/photo/analyze", files=files)
            st.session_state["last_photo"] = result
        except Exception as exc:
            friendly_error(exc)
            return

    result = st.session_state.get("last_photo")
    if not result:
        return

    st.subheader(result.get("verdict") or "Вердикт")
    scores = result.get("scores") or {}
    cols = st.columns(3)
    labels = [
        ("atmosphere", "атмосфера"),
        ("composition", "композиция"),
        ("light", "свет"),
        ("palette", "палитра"),
        ("storytelling", "история"),
        ("aesthetic_fit", "в эстетике"),
    ]
    for i, (key, label) in enumerate(labels):
        cols[i % 3].metric(label, scores.get(key, "—"))

    if result.get("series_comparison"):
        st.write(result["series_comparison"])
        if result.get("best_in_series") is not None:
            st.caption(f"Лучший в серии: кадр {int(result['best_in_series']) + 1}")

    st.markdown(f"**Направление для подписи:** {result.get('caption_direction') or '—'}")
    why_block(result.get("why"))
    feedback_buttons(result.get("suggestion_id"), "photo_main")

    for i, adv in enumerate(result.get("advice_suggestions") or []):
        st.markdown(f"· {adv.get('text')}")
        feedback_buttons(adv.get("suggestion_id"), f"photo_adv_{i}")

    if st.button("набросать подпись", key="photo_to_caption"):
        direction = (result.get("caption_direction") or "").strip()
        verdict = (result.get("verdict") or "").strip()
        draft = direction
        if verdict and verdict not in draft:
            draft = f"{verdict}\n\n{direction}".strip() if direction else verdict
        st.session_state["draft_from_idea"] = draft or "…"
        st.session_state["nav_to"] = "Текст"
        st.rerun()


def _publish_block(
    *,
    message: str,
    key_prefix: str,
    plan_item_id: int | None = None,
) -> None:
    """Блок публикации в VK с явным подтверждением."""
    st.markdown("#### В VK")
    st.caption("Публикация только после подтверждения")
    photos = st.file_uploader(
        "Фото к посту (необязательно)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key=f"{key_prefix}_photos",
    )
    schedule_date = st.text_input(
        "Отложить (ГГГГ-ММ-ДД), пусто — сразу",
        key=f"{key_prefix}_sched_date",
        placeholder="2026-08-22",
    )
    schedule_time = st.text_input(
        "Время (ЧЧ:ММ), МСК",
        key=f"{key_prefix}_sched_time",
        value="12:00",
    )
    confirm = st.checkbox("подтверждаю публикацию", key=f"{key_prefix}_confirm")
    if not st.button("опубликовать в VK", key=f"{key_prefix}_go"):
        return
    if not message.strip():
        st.warning("Нужен текст поста")
        return
    if not confirm:
        st.warning("Нужна галочка подтверждения")
        return

    publish_unix: int | None = None
    if schedule_date.strip():
        try:
            day = datetime.strptime(schedule_date.strip(), "%Y-%m-%d")
            hour, minute = 12, 0
            if schedule_time.strip():
                parts = schedule_time.strip().split(":")
                hour, minute = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
            when = day.replace(hour=hour, minute=minute)
            publish_unix = int(when.timestamp())
        except ValueError:
            st.warning("Формат даты/времени: ГГГГ-ММ-ДД и ЧЧ:ММ")
            return

    data: dict[str, Any] = {
        "confirm": "true",
        "message": message,
    }
    if publish_unix is not None:
        data["publish_date_unix"] = str(publish_unix)
    if plan_item_id is not None:
        data["plan_item_id"] = str(plan_item_id)

    files = None
    if photos:
        files = [
            ("files", (up.name, up.getvalue(), up.type or "image/jpeg")) for up in photos
        ]

    try:
        with st.spinner("Публикация…"):
            result = api_post_form("/publish/form", data=data, files=files)
        st.success(f"Опубликовано: {result.get('vk_post_id') or 'ok'}")
        if result.get("photos_warning"):
            st.info(result["photos_warning"])
        elif result.get("photos_attached"):
            st.caption(f"Фото: {result['photos_attached']}")
    except Exception as exc:
        friendly_error(exc)


def page_text() -> None:
    st.header("Текст")
    st.caption("Редактура черновика с сохранением голоса")

    default = ""
    if st.session_state.get("draft_from_idea"):
        default = st.session_state.pop("draft_from_idea")

    draft = st.text_area(
        "Черновик",
        value=default or st.session_state.get("current_draft", ""),
        height=220,
        placeholder="Вставь черновик",
    )
    topic = st.text_input("Тема (необязательно)", placeholder="например: завтрак")
    plan_id = st.session_state.get("plan_item_id")

    col_a, col_b = st.columns([1, 2])
    with col_a:
        run = st.button("отредактировать")
    if run and draft.strip():
        try:
            with st.spinner("Редактура…"):
                result = api_post(
                    "/text/edit",
                    json={
                        "draft": draft,
                        "topic_hint": topic,
                        "plan_item_id": plan_id,
                    },
                )
            st.session_state["last_edit"] = result
            st.session_state["current_draft"] = result.get("revised_text") or draft
        except Exception as exc:
            friendly_error(exc)

    result = st.session_state.get("last_edit")
    if not result:
        if draft.strip():
            _publish_block(message=draft, key_prefix="text_raw", plan_item_id=plan_id)
        else:
            empty_state("Вставь черновик.")
        _show_voice_sidebar()
        return

    st.subheader("Результат")
    voice_ok = result.get("in_voice")
    st.markdown(
        f"{'В голосе' if voice_ok else 'Выбивается'} — {result.get('voice_notes') or ''}"
    )
    revised = st.text_area("Отредактированный текст", value=result.get("revised_text") or "", height=200)
    st.session_state["current_draft"] = revised

    openings = result.get("alternative_openings") or []
    if openings:
        st.markdown("**Другие первые строки**")
        for line in openings:
            st.markdown(f"· {line}")

    for i, edit in enumerate(result.get("edits") or []):
        with st.expander(edit.get("explanation") or f"правка {i+1}"):
            st.caption("было")
            st.write(edit.get("original"))
            st.caption("стало")
            st.write(edit.get("revised"))
            c1, c2 = st.columns(2)
            sid = edit.get("suggestion_id")
            if sid:
                with c1:
                    if st.button("принять", key=f"edit_yes_{sid}"):
                        try:
                            api_post(
                                "/text/apply-edit",
                                json={
                                    "suggestion_id": sid,
                                    "accepted": True,
                                    "current_text": revised,
                                },
                            )
                            st.success("Принято")
                        except Exception as exc:
                            friendly_error(exc)
                with c2:
                    if st.button("отклонить", key=f"edit_no_{sid}"):
                        try:
                            api_post(
                                "/text/apply-edit",
                                json={
                                    "suggestion_id": sid,
                                    "accepted": False,
                                    "current_text": revised,
                                },
                            )
                            st.info("Пропущено")
                        except Exception as exc:
                            friendly_error(exc)

    why_block(result.get("why"))
    feedback_buttons(result.get("suggestion_id"), "edit_main")
    _publish_block(message=revised, key_prefix="text_rev", plan_item_id=plan_id)
    _show_voice_sidebar()


def _show_voice_sidebar() -> None:
    try:
        voice = api_get("/voice")
    except Exception:
        return
    with st.expander("Профиль голоса"):
        profile = voice.get("profile") or {}
        st.caption(f"версия {voice.get('version')}")
        st.write(f"Тон: {profile.get('tone', '—')}")
        st.write(f"Обращение: {profile.get('address', '—')}")
        st.write(f"Эмодзи: {profile.get('emoji_habits', '—')}")
        shades = profile.get("shades") or {}
        if shades:
            st.caption("Оттенки")
            for k, v in shades.items():
                st.markdown(f"· **{k}**: {v}")


def page_analytics() -> None:
    st.header("Аналитика")
    st.caption("Вовлечённость и выводы по архиву")
    try:
        with st.spinner("Загрузка…"):
            data = api_get("/analytics", with_report=True)
    except Exception as exc:
        friendly_error(exc)
        return

    if data.get("posts_count", 0) == 0:
        empty_state("Нет постов. Сначала импорт из VK.")
        return

    series = data.get("series") or []
    if series:
        fig = px.line(
            series,
            x="date",
            y="engagement",
            markers=True,
            title="Вовлечённость",
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(243,244,246,0.8)",
            font_family="IBM Plex Sans",
            font_color="#14181c",
        )
        st.plotly_chart(fig, use_container_width=True)

    tops = data.get("top_posts") or []
    if tops:
        st.subheader("Топ-посты")
        for p in tops:
            st.markdown(
                f"**{p.get('theme') or 'без темы'}** · eng {p.get('engagement', 0):.0f} — "
                f"{(p.get('text') or '')[:120]}"
            )

    report = data.get("report")
    if report:
        st.subheader("Выводы")
        st.write(report.get("portrait") or "")
        why_block(report.get("why"))
        feedback_buttons(report.get("suggestion_id"), "audience")
        for block, title in (
            ("what_works", "Что работает"),
            ("frequent_questions", "Частые вопросы"),
            ("unmet_needs", "Незакрытые запросы"),
            ("recommendations", "Делать чаще"),
        ):
            items = report.get(block) or []
            if items:
                st.markdown(f"**{title}**")
                for line in items:
                    st.markdown(f"· {line}")
        for i, insight in enumerate(report.get("insights") or []):
            with st.expander(insight.get("title") or f"инсайт {i+1}"):
                st.write(insight.get("body"))
                st.caption(f"Данные: {insight.get('based_on')}")
                why_block(insight.get("why"))


def page_ideas() -> None:
    st.header("Идеи и план")
    st.caption("Идеи → план → черновик → публикация")

    st.subheader("Из архива к сезону")
    if st.button("показать сезонные", key="load_seasonal"):
        try:
            with st.spinner("Поиск…"):
                seasonal = api_get("/archive/seasonal")
            st.session_state["seasonal_archive"] = seasonal
        except Exception as exc:
            friendly_error(exc)

    seasonal = st.session_state.get("seasonal_archive")
    if seasonal:
        why_block(seasonal.get("why"))
        hits = seasonal.get("hits") or []
        if not hits:
            st.caption("Ничего подходящего в архиве")
        for i, hit in enumerate(hits):
            with st.container():
                theme = hit.get("theme") or "без темы"
                st.markdown(
                    f"**{theme}** · eng {float(hit.get('engagement') or 0):.0f}"
                )
                st.write(hit.get("text_preview") or "")
                st.caption(hit.get("why_relevant") or "")
                b1, b2 = st.columns(2)
                with b1:
                    if st.button("в план", key=f"arch_plan_{hit.get('post_id')}_{i}"):
                        try:
                            item = api_post(
                                "/plan/from-text",
                                json={
                                    "title": theme[:240],
                                    "draft_text": hit.get("text_preview") or "",
                                },
                            )
                            st.session_state["plan_item_id"] = item.get("id")
                            st.success("В плане")
                        except Exception as exc:
                            friendly_error(exc)
                with b2:
                    if st.button("к черновику", key=f"arch_draft_{hit.get('post_id')}_{i}"):
                        st.session_state["draft_from_idea"] = hit.get("text_preview") or theme
                        st.session_state["nav_to"] = "Текст"
                        st.rerun()

    st.subheader("Новые идеи")
    c1, c2 = st.columns(2)
    with c1:
        count = st.slider("Сколько идей", 2, 6, 3)
    with c2:
        if st.button("предложить идеи"):
            try:
                with st.spinner("Генерация…"):
                    batch = api_post("/ideas/generate", json={"count": count})
                st.session_state["idea_batch"] = batch.get("ideas") or []
            except Exception as exc:
                friendly_error(exc)

    ideas = st.session_state.get("idea_batch") or []
    if not ideas:
        empty_state("Нажми «предложить идеи».")
    for i, idea in enumerate(ideas):
        with st.container():
            st.markdown(f"### {idea.get('theme')}")
            st.write(idea.get("description") or "")
            st.caption(
                f"{idea.get('format') or ''} · усилие: {idea.get('effort')} · "
                f"{idea.get('personal_angle') or ''}"
            )
            st.write(f"Визуал: {idea.get('visual') or '—'}")
            st.write(f"Почему сейчас: {idea.get('why_now') or ''}")
            why_block(idea.get("why"))
            feedback_buttons(idea.get("suggestion_id"), f"idea_{i}")
            b1, b2 = st.columns(2)
            with b1:
                if idea.get("id") and st.button("в план", key=f"idea_plan_{idea['id']}"):
                    try:
                        item = api_post(f"/ideas/{idea['id']}/to-plan")
                        st.session_state["plan_item_id"] = item.get("id")
                        st.success("В плане")
                    except Exception as exc:
                        friendly_error(exc)
            with b2:
                if st.button("к черновику", key=f"idea_draft_{i}"):
                    st.session_state["draft_from_idea"] = (
                        f"{idea.get('theme')}\n\n{idea.get('personal_angle') or ''}\n\n"
                        f"{idea.get('description') or ''}"
                    )
                    st.session_state["nav_to"] = "Текст"
                    st.rerun()

    _render_weekly_plan()


def _week_bounds(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _parse_plan_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _render_plan_item(item: dict[str, Any]) -> None:
    status_raw = item.get("status") or "conceived"
    label = _STATUS_LABEL.get(status_raw, status_raw)
    with st.expander(f"{item.get('title')} · {label}"):
        status = st.selectbox(
            "Статус",
            ["conceived", "written", "published"],
            format_func=lambda s: _STATUS_LABEL.get(s, s),
            index=["conceived", "written", "published"].index(status_raw),
            key=f"status_{item['id']}",
        )
        draft = st.text_area(
            "Черновик",
            value=item.get("draft_text") or "",
            key=f"draft_{item['id']}",
        )
        date_val = st.text_input(
            "Дата (ГГГГ-ММ-ДД)",
            value=item.get("scheduled_date") or "",
            key=f"date_{item['id']}",
        )
        if st.button("сохранить", key=f"save_plan_{item['id']}"):
            try:
                api_patch(
                    f"/plan/{item['id']}",
                    json={
                        "status": status,
                        "draft_text": draft,
                        "scheduled_date": date_val or None,
                    },
                )
                st.success("Сохранено")
            except Exception as exc:
                friendly_error(exc)
        if st.button("редактировать текст", key=f"to_text_{item['id']}"):
            st.session_state["draft_from_idea"] = draft or item.get("title")
            st.session_state["plan_item_id"] = item["id"]
            st.session_state["nav_to"] = "Текст"
            st.rerun()
        _publish_block(
            message=draft or item.get("title") or "",
            key_prefix=f"plan_pub_{item['id']}",
            plan_item_id=item["id"],
        )


def _render_weekly_plan() -> None:
    st.subheader("План на неделю")
    try:
        hint_data = api_get("/rhythm/hint")
        st.caption(hint_data.get("hint") or "")
    except Exception:
        pass

    try:
        plan = api_get("/plan")
    except Exception as exc:
        friendly_error(exc)
        return
    if not plan:
        empty_state("План пуст.")
        return

    monday, sunday = _week_bounds()
    by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    undated: list[dict[str, Any]] = []
    outside: list[dict[str, Any]] = []

    for item in plan:
        d = _parse_plan_date(item.get("scheduled_date"))
        if d is None:
            undated.append(item)
        elif monday <= d <= sunday:
            by_day[d].append(item)
        else:
            outside.append(item)

    for offset in range(7):
        day = monday + timedelta(days=offset)
        items = by_day.get(day) or []
        st.markdown(f"**{_WEEKDAYS_RU[offset]} · {day.strftime('%d.%m')}**")
        if not items:
            st.caption("—")
        else:
            for item in items:
                _render_plan_item(item)

    if undated:
        st.markdown("**Без даты**")
        for item in undated:
            _render_plan_item(item)

    if outside:
        with st.expander("Другие даты"):
            for item in outside:
                _render_plan_item(item)


def page_concierge() -> None:
    st.header("ЛС")
    st.caption("Черновик ответа. Отправка только вручную в VK.")

    st.subheader("Входящие")
    if st.button("обновить", key="inbox_refresh"):
        try:
            inbox = api_get("/concierge/inbox")
            st.session_state["inbox"] = inbox
        except Exception as exc:
            friendly_error(exc)

    inbox = st.session_state.get("inbox")
    if inbox is not None:
        if not inbox.get("available", True):
            st.info(inbox.get("message") or "Нет доступа к ЛС — вставь текст вручную")
        else:
            items = inbox.get("items") or []
            if not items:
                st.caption("Диалогов нет")
            for i, row in enumerate(items):
                preview = row.get("preview") or ""
                unread = int(row.get("unread") or 0)
                meta = row.get("date") or ""
                label = f"{'● ' if unread else ''}{preview[:80]}"
                if st.button(label, key=f"inbox_pick_{row.get('peer_id')}_{i}"):
                    st.session_state["concierge_input"] = preview
                    st.rerun()
                if meta:
                    st.caption(str(meta)[:16])

    message = st.text_area(
        "Входящее сообщение",
        height=160,
        placeholder="Текст из ЛС",
        key="concierge_input",
    )
    if st.button("черновик ответа"):
        if not message.strip():
            st.warning("Нужен текст сообщения")
            return
        try:
            with st.spinner("Черновик…"):
                reply = api_post("/concierge", json={"message_text": message.strip()})
            st.session_state["concierge_reply"] = reply
        except Exception as exc:
            friendly_error(exc)
            return

    reply = st.session_state.get("concierge_reply")
    if not reply:
        empty_state("Вставь сообщение или выбери из входящих.")
        return

    st.markdown(f"**Тип:** {reply.get('category_label') or reply.get('category')}")
    if reply.get("related_post"):
        st.caption(f"Связанный пост: {reply['related_post']}")
    st.text_area(
        "Черновик ответа",
        value=reply.get("draft_reply") or "",
        height=180,
        key="concierge_draft_out",
    )
    why_block(reply.get("why"))
    feedback_buttons(reply.get("suggestion_id"), "concierge")

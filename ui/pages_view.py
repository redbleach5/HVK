"""Страницы дашборда Streamlit."""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_UI_DIR = Path(__file__).resolve().parent
_ROOT = _UI_DIR.parent
sys.path[:] = [p for p in sys.path if Path(p).resolve() != _UI_DIR]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import plotly.express as px
import streamlit as st

from app.context.engine import current_season, format_date_ru
from ui.api_client import api_get, api_patch, api_post, api_post_form, friendly_error, vk_is_configured
from ui.desk import save_desk
from ui.theme import empty_state, feedback_buttons, voice_status_widget, why_block

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

    digest_text = data.get("digest") or ""
    if not digest_text:
        try:
            posts_n = int(api_get("/onboarding/status").get("posts_imported") or 0)
        except Exception as exc:
            friendly_error(exc)
            posts_n = -1
        if posts_n == 0:
            digest_text = (
                "Я ещё не читала твои тексты — без них это будет угадайка. "
                "Вставь несколько своих постов, и сводка станет настоящей 🤍"
            )
        elif posts_n < 0:
            digest_text = (
                f"Сегодня {format_date_ru()}, сезон — {current_season()}. "
                "Сводка ещё не собралась — загляни чуть позже."
            )
        else:
            digest_text = (
                f"Сегодня {format_date_ru()}, сезон — {current_season()}. "
                "Загляни, когда будет тихое утро — соберу заметки. "
                "Пока в архиве уже есть твои тексты, но голос ещё дособирается."
            )
    with st.container(border=True):
        st.markdown(digest_text)
        for h in data.get("highlights") or []:
            text = h.get("text") if isinstance(h, dict) else str(h)
            st.markdown(f"· {text}")
        why_block(data.get("why"))

    voice_status_widget()

    ideas = data.get("ideas") or []
    if ideas:
        st.subheader("Идеи")
        for i, idea in enumerate(ideas):
            with st.container(border=True):
                st.markdown(f"**{idea.get('theme')}** · {idea.get('format') or 'формат свободный'}")
                st.write(idea.get("description") or "")
                if idea.get("why_now"):
                    st.caption(idea.get("why_now"))
                why_block(idea.get("why"))
                feedback_buttons(idea.get("suggestion_id"), f"today_idea_{i}")
                if idea.get("id") and st.button("в план", key=f"today_plan_{idea['id']}", type="secondary"):
                    try:
                        api_post(f"/ideas/{idea['id']}/to-plan")
                        st.session_state["active_idea"] = idea
                        st.success("В плане")
                    except Exception as exc:
                        friendly_error(exc)
    else:
        empty_state(
            "Карточек в этой сводке ещё нет. Когда захочешь — вкладка «Идеи и план», "
            "я оперся на твои тексты, не на выдумку."
        )

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
    st.caption("Разбор кадра или серии. Первый раз может подождать — это нормально.")
    uploads = st.file_uploader(
        "Фото",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    # Превью загруженных фото ДО кнопки «разобрать»
    if uploads:
        preview_cols = st.columns(min(4, len(uploads)))
        for i, up in enumerate(uploads):
            with preview_cols[i % 4]:
                st.image(up, use_container_width=True)

    if not uploads:
        empty_state(
            '<span class="tr-empty-icon">📷</span>Здесь пока тихо — загрузи кадр, разберём без спешки 🤍',
        )
        return

    if st.button("разобрать", key="photo_analyze"):
        files = []
        for up in uploads:
            files.append(("files", (up.name, up.getvalue(), up.type or "image/jpeg")))
        try:
            with st.spinner("смотрю кадр…"):
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
        st.info(result["series_comparison"])
        if result.get("best_in_series") is not None:
            st.caption(f"Лучший в серии: кадр {int(result['best_in_series']) + 1}")
    elif result.get("best_in_series") is not None:
        st.caption(f"Лучший кадр: {int(result['best_in_series']) + 1}")

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
    if not vk_is_configured():
        empty_state("VK не подключён — копируй текст вручную, когда будешь готова.")
        return
    st.markdown("#### В VK")
    st.caption("Публикация только после подтверждения")
    photos = st.file_uploader(
        "Фото к посту (необязательно)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key=f"{key_prefix}_photos",
    )
    schedule_date = st.date_input(
        "Отложить",
        key=f"{key_prefix}_sched_date",
    )
    schedule_time = st.time_input(
        "Время",
        key=f"{key_prefix}_sched_time",
        value=datetime.strptime("12:00", "%H:%M").time(),
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
    if schedule_date:
        try:
            day = datetime.combine(schedule_date, datetime.min.time())
            hour = schedule_time.hour if schedule_time else 12
            minute = schedule_time.minute if schedule_time else 0
            when = day.replace(hour=hour, minute=minute)
            publish_unix = int(when.timestamp())
        except Exception:
            st.warning("Не получилось собрать дату публикации")
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
        st.session_state["current_draft"] = default
        save_desk()

    draft = st.text_area(
        "Черновик",
        key="current_draft",
        height=220,
        placeholder="Вставь черновик",
        on_change=save_desk,
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
            st.session_state["revised_text"] = result.get("revised_text") or draft
            save_desk()
        except Exception as exc:
            friendly_error(exc)

    result = st.session_state.get("last_edit")
    if not result:
        if draft.strip():
            _publish_block(message=draft, key_prefix="text_raw", plan_item_id=plan_id)
        else:
            empty_state(
                "Вставь черновик — бережно поправлю, опираясь на твой голос."
            )
        return

    st.subheader("Результат")
    voice_ok = result.get("in_voice")
    st.markdown(
        f"{'В голосе' if voice_ok else 'Выбивается'} — {result.get('voice_notes') or ''}"
    )
    if "revised_text" not in st.session_state:
        st.session_state["revised_text"] = result.get("revised_text") or ""
    revised = st.text_area("Отредактированный текст", key="revised_text", height=200)
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
                    if st.button("взять", key=f"edit_yes_{sid}"):
                        try:
                            out = api_post(
                                "/text/apply-edit",
                                json={
                                    "suggestion_id": sid,
                                    "accepted": True,
                                    "current_text": revised,
                                },
                            )
                            new_text = out.get("current_text") or revised
                            st.session_state["current_draft"] = new_text
                            st.session_state["last_edit"]["revised_text"] = new_text
                            st.success("В тексте")
                            st.rerun()
                        except Exception as exc:
                            friendly_error(exc)
                with c2:
                    if st.button("оставить как было", key=f"edit_no_{sid}"):
                        try:
                            out = api_post(
                                "/text/apply-edit",
                                json={
                                    "suggestion_id": sid,
                                    "accepted": False,
                                    "current_text": revised,
                                },
                            )
                            new_text = out.get("current_text") or revised
                            st.session_state["current_draft"] = new_text
                            st.session_state["last_edit"]["revised_text"] = new_text
                            st.info("Вернула")
                            st.rerun()
                        except Exception as exc:
                            friendly_error(exc)

    why_block(result.get("why"))
    feedback_buttons(result.get("suggestion_id"), "edit_main")
    _publish_block(message=revised, key_prefix="text_rev", plan_item_id=plan_id)


def page_analytics() -> None:
    st.header("Аналитика")
    st.caption("Вовлечённость и выводы по архиву")
    try:
        with st.spinner("Загрузка…"):
            data = api_get("/analytics", with_report=False)
    except Exception as exc:
        friendly_error(exc)
        return

    if data.get("posts_count", 0) == 0:
        empty_state("Здесь пока тихо — вставь свои посты, и я буду опираться на них.")
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
            plot_bgcolor="rgba(250,248,245,0.9)",
            font_family="Georgia",
            font_color="#3d3229",
        )
        st.plotly_chart(fig, use_container_width=True)

    tops = data.get("top_posts") or []
    if tops:
        st.subheader("Топ-посты")
        for p in tops:
            st.markdown(
                f"**{p.get('theme') or 'без темы'}** · отклик {p.get('engagement', 0):.0f} — "
                f"{(p.get('text') or '')[:120]}"
            )

    # Кнопка для загрузки отчёта
    if st.button("сделать выводы"):
        try:
            with st.spinner("Смотрю архив…"):
                report_data = api_get("/analytics", with_report=True)
            report = report_data.get("report")
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
        except Exception as exc:
            friendly_error(exc)


def page_ideas() -> None:
    st.header("Идеи и план")
    st.caption("Идеи → план → черновик → публикация")

    st.subheader("Из архива к сезону")
    if st.button("показать сезонные", key="load_seasonal"):
        try:
            with st.spinner("Ищу архив…"):
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
            with st.container(border=True):
                theme = hit.get("theme") or "без темы"
                st.markdown(
                    f"**{theme}** · отклик {float(hit.get('engagement') or 0):.0f}"
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
                            save_desk()
                            st.success("В плане")
                        except Exception as exc:
                            friendly_error(exc)
                with b2:
                    if st.button("к черновику", key=f"arch_draft_{hit.get('post_id')}_{i}"):
                        st.session_state["draft_from_idea"] = hit.get("text_preview") or theme
                        st.session_state["nav_to"] = "Текст"
                        st.rerun()

    st.subheader("Новые идеи")
    try:
        posts_n = int(api_get("/onboarding/status").get("posts_imported") or 0)
    except Exception as exc:
        friendly_error(exc)
        return
    if posts_n == 0:
        empty_state(
            "Сначала нужны твои тексты — иначе идеи будут с потолка, "
            "а не из твоей жизни. Вставь 3–8 постов 🤍"
        )
    else:
        c1, c2 = st.columns(2)
        with c1:
            count = st.slider("Сколько идей", 2, 6, 3)
        with c2:
            if st.button("предложить идеи"):
                try:
                    with st.spinner("Генерирую идеи…"):
                        batch = api_post("/ideas/generate", json={"count": count})
                    st.session_state["idea_batch"] = batch.get("ideas") or []
                except Exception as exc:
                    friendly_error(exc)

        ideas = st.session_state.get("idea_batch") or []
        if not ideas:
            try:
                ideas = api_get("/ideas").get("ideas") or []
                if ideas:
                    st.session_state["idea_batch"] = ideas
            except Exception as exc:
                friendly_error(exc)
                ideas = []
        if not ideas:
            empty_state(
                "Нажми «предложить идеи» — я оперусь на твой архив и сезон."
            )
        for i, idea in enumerate(ideas):
            with st.container(border=True):
                st.markdown(f"### {idea.get('theme')}")
                st.write(idea.get("description") or "")
                st.caption(
                    f"{idea.get('format') or ''} · усилие: {idea.get('effort')} · "
                    f"{idea.get('personal_angle') or ''}"
                )
                if idea.get("visual"):
                    st.caption(f"Визуал: {idea.get('visual')}")
                if idea.get("why_now"):
                    st.write(f"Почему сейчас: {idea.get('why_now')}")
                why_block(idea.get("why"))
                feedback_buttons(idea.get("suggestion_id"), f"idea_{i}")
                b1, b2 = st.columns(2)
                with b1:
                    if idea.get("id") and st.button("в план", key=f"idea_plan_{idea['id']}", type="secondary"):
                        try:
                            item = api_post(f"/ideas/{idea['id']}/to-plan")
                            st.session_state["plan_item_id"] = item.get("id")
                            save_desk()
                            st.success("В плане")
                        except Exception as exc:
                            friendly_error(exc)
                with b2:
                    if st.button("к черновику", key=f"idea_draft_{i}", type="secondary"):
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
        raw_date = item.get("scheduled_date")
        date_default = date.fromisoformat(raw_date[:10]) if raw_date else date.today()
        date_val = st.date_input(
            "Дата",
            value=date_default,
            key=f"date_{item['id']}",
        )
        if st.button("сохранить", key=f"save_plan_{item['id']}"):
            try:
                api_patch(
                    f"/plan/{item['id']}",
                    json={
                        "status": status,
                        "draft_text": draft,
                        "scheduled_date": date_val.isoformat() if date_val else None,
                    },
                )
                st.success("Сохранено")
            except Exception as exc:
                friendly_error(exc)
        if st.button("редактировать текст", key=f"to_text_{item['id']}", type="secondary"):
            st.session_state["draft_from_idea"] = draft or item.get("title")
            st.session_state["plan_item_id"] = item["id"]
            save_desk()
            st.session_state["nav_to"] = "Текст"
            st.rerun()
        _publish_block(
            message=draft or item.get("title") or "",
            key_prefix=f"plan_pub_{item['id']}",
            plan_item_id=item["id"],
        )


def _plan_chip(item: dict[str, Any]) -> None:
    title = (item.get("title") or "без названия").strip()
    if len(title) > 42:
        title = title[:40].rstrip() + "…"
    label = _STATUS_LABEL.get(item.get("status") or "conceived", "")
    st.markdown(
        f'<div class="tr-chip"><strong>{title}</strong><br>{label}</div>',
        unsafe_allow_html=True,
    )


def _render_weekly_plan() -> None:
    st.subheader("План на неделю")
    try:
        hint_data = api_get("/rhythm/hint")
        hint = (hint_data.get("hint") or "").strip()
        if hint:
            st.caption(hint)
    except Exception as exc:
        friendly_error(exc)

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

    cols = st.columns(7)
    for offset in range(7):
        day = monday + timedelta(days=offset)
        items = by_day.get(day) or []
        with cols[offset]:
            st.markdown(
                f'<div class="tr-day">{_WEEKDAYS_RU[offset]} · {day.strftime("%d.%m")}</div>',
                unsafe_allow_html=True,
            )
            if not items:
                st.caption("—")
            else:
                for item in items:
                    _plan_chip(item)

    editable = undated + [i for day_items in by_day.values() for i in day_items] + outside
    if editable:
        st.markdown("##### Правки")
        st.caption("Сетка сверху — обзор. Ниже можно менять статус, дату и черновик.")
        for item in undated:
            _render_plan_item(item)
        for offset in range(7):
            day = monday + timedelta(days=offset)
            for item in by_day.get(day) or []:
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




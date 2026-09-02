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
from ui.api_client import api_delete, api_get, api_patch, api_post, api_post_form, friendly_error, vk_is_configured
from ui.desk import save_desk
from ui.theme import (
    char_counter,
    copy_to_clipboard_button,
    empty_state,
    feedback_buttons,
    toast,
    voice_status_widget,
    why_block,
)

_WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
_STATUS_LABEL = {
    "conceived": "задумано",
    "written": "написано",
    "published": "опубликовано",
}
_STATUS_ORDER = ["conceived", "written", "published"]


def _safe_status_index(status_raw: str) -> int:
    """Безопасный индекс для selectbox — не падает на неизвестном статусе."""
    if status_raw in _STATUS_ORDER:
        return _STATUS_ORDER.index(status_raw)
    return 0


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

    with st.expander("как ты звучишь", expanded=False):
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
                        st.session_state["_toast"] = "В плане"
                        st.rerun()
                    except Exception as exc:
                        friendly_error(exc)
    else:
        empty_state(
            "Карточек в этой сводке ещё нет. Когда захочешь — спроси в чате про идеи: "
            "я оперлась на твои тексты, не на выдумку."
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
                created = str(a.get("created_at", ""))[:16].replace("T", " ")
                st.caption(f"{created} — {a.get('summary')}")


def _render_photo_grid(uploads: list) -> None:
    """Адаптивная сетка превью фото."""
    if not uploads:
        return
    n = min(len(uploads), 8)
    cols = st.columns(n)
    for i, up in enumerate(uploads[:n]):
        with cols[i]:
            st.image(up, use_container_width=True)


def page_photo() -> None:
    st.header("Фото")
    st.caption("Разбор кадра или серии. Первый раз может подождать — это нормально.")
    uploads = st.file_uploader(
        "Фото",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="photo_uploads",
    )

    # Превью загруженных фото ДО кнопки «разобрать» — адаптивная сетка
    if uploads:
        _render_photo_grid(list(uploads))

    if not uploads:
        st.caption("Загрузи кадр — разберём без спешки.")
        if st.session_state.get("last_photo"):
            if st.button("показать последний разбор", type="secondary"):
                st.rerun()
        return

    col_a, col_b = st.columns([1, 2])
    with col_a:
        if st.button("разобрать", key="photo_analyze", type="primary"):
            files = []
            for up in uploads:
                files.append(("files", (up.name, up.getvalue(), up.type or "image/jpeg")))
            try:
                with st.spinner("смотрю кадр…"):
                    result = api_post("/photo/analyze", files=files)
                st.session_state["last_photo"] = result
                st.rerun()
            except Exception as exc:
                friendly_error(exc)
                return
    with col_b:
        # Тихий сброс — если было что-то разобрано, можно «начать заново»
        if st.session_state.get("last_photo"):
            if st.button("разобрать другой кадр", key="photo_reset", type="secondary"):
                # Streamlit file_uploader не умеет очищаться из кода —
                # поэтому даём пользователю выбрать: либо продолжить, либо сменить файлы
                st.session_state.pop("last_photo", None)
                st.session_state["photo_uploads"] = []
                st.rerun()

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
    if result.get("caption_direction"):
        copy_to_clipboard_button(
            str(result.get("caption_direction")),
            key="photo_cap_copy",
            label="скопировать подпись",
        )
    why_block(result.get("why"))
    feedback_buttons(result.get("suggestion_id"), "photo_main")

    for i, adv in enumerate(result.get("advice_suggestions") or []):
        st.markdown(f"· {adv.get('text')}")
        feedback_buttons(adv.get("suggestion_id"), f"photo_adv_{i}")

    if st.button("набросать подпись", key="photo_to_caption", type="secondary"):
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
        st.markdown("#### Опубликовать")
        st.caption("VK не подключён — копируй текст и выложи сама, когда будешь готова.")
        if message.strip():
            copy_to_clipboard_button(message, key=f"{key_prefix}_copy", label="скопировать текст")
        return
    st.markdown("#### В VK")
    st.caption("Публикация только после подтверждения")
    photos = st.file_uploader(
        "Фото к посту (необязательно)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key=f"{key_prefix}_photos",
    )
    today = date.today()
    schedule_date = st.date_input(
        "Отложить",
        key=f"{key_prefix}_sched_date",
        min_value=today,
        value=today,
    )
    schedule_time = st.time_input(
        "Время",
        key=f"{key_prefix}_sched_time",
        value=datetime.strptime("12:00", "%H:%M").time(),
    )
    confirm = st.checkbox("подтверждаю публикацию", key=f"{key_prefix}_confirm")
    if not st.button("опубликовать в VK", key=f"{key_prefix}_go", type="primary"):
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
        st.session_state["_toast"] = "Опубликовано"
        if result.get("photos_warning"):
            st.info(result["photos_warning"])
        elif result.get("photos_attached"):
            st.caption(f"Фото: {result['photos_attached']}")
        st.rerun()
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
    st.markdown(char_counter(draft), unsafe_allow_html=True)
    topic = st.text_input("Тема (необязательно)", placeholder="например: завтрак")
    plan_id = st.session_state.get("plan_item_id")

    col_a, col_b, col_c = st.columns([1, 1, 2])
    with col_a:
        run = st.button("отредактировать", type="primary")
    with col_b:
        if draft.strip():
            copy_to_clipboard_button(draft, key="draft_copy", label="копировать")
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
            st.session_state["_revised_text_widget"] = result.get("revised_text") or draft
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
    # ИСПРАВЛЕНО: раньше тот же ключ был и в session_state, и как ключ виджета —
    # Streamlit ругался на коллизию. Теперь отдельный _widget-ключ.
    if "_revised_text_widget" not in st.session_state:
        st.session_state["_revised_text_widget"] = result.get("revised_text") or ""
    revised = st.text_area(
        "Отредактированный текст",
        key="_revised_text_widget",
        height=200,
    )
    st.session_state["current_draft"] = revised
    st.markdown(char_counter(revised), unsafe_allow_html=True)

    col_copy, _ = st.columns([1, 3])
    with col_copy:
        if revised and revised.strip():
            copy_to_clipboard_button(revised, key="revised_copy", label="копировать")

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
                            st.session_state["_revised_text_widget"] = new_text
                            st.session_state["_toast"] = "В тексте"
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
                            st.session_state["_revised_text_widget"] = new_text
                            st.session_state["_toast"] = "Вернула"
                            st.rerun()
                        except Exception as exc:
                            friendly_error(exc)

    why_block(result.get("why"))
    feedback_buttons(result.get("suggestion_id"), "edit_main")
    _publish_block(message=revised, key_prefix="text_rev", plan_item_id=plan_id)


def _build_engagement_fig(series: list[dict], metric: str, title: str):
    """График вовлечённости в тёплой палитре стола."""
    color = "#8B7355"
    fig = px.line(
        series,
        x="date",
        y=metric,
        markers=True,
        title=title,
    )
    fig.update_traces(
        line_color=color,
        marker_color=color,
        marker_size=7,
        line_width=2,
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_family="Source Sans 3, sans-serif",
        font_color="#3d3229",
        margin=dict(l=8, r=8, t=42, b=8),
        height=320,
        title_font=dict(size=16, color="#3d3229"),
        xaxis=dict(
            gridcolor="rgba(139,115,85,0.12)",
            zerolinecolor="rgba(139,115,85,0.18)",
            tickformat="%d.%m",
        ),
        yaxis=dict(
            gridcolor="rgba(139,115,85,0.12)",
            zerolinecolor="rgba(139,115,85,0.18)",
        ),
        hoverlabel=dict(
            bgcolor="#fffaf4",
            font_color="#3d3229",
            bordercolor="#e6dcd0",
        ),
    )
    return fig


def page_analytics() -> None:
    st.header("Аналитика")
    st.caption("Что заходило — по архиву")

    try:
        with st.spinner("Загрузка…"):
            data = api_get("/analytics", with_report="false")
    except Exception as exc:
        friendly_error(exc)
        return

    if data.get("posts_count", 0) == 0:
        empty_state("Здесь пока тихо — вставь свои посты, и я буду опираться на них.")
        return

    series = data.get("series") or []
    if series:
        fig = _build_engagement_fig(series, "engagement", "Вовлечённость")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Пока мало публикаций с датой.")

    tops = data.get("top_posts") or []
    if tops:
        st.subheader("Топ-посты")
        for p in tops:
            st.markdown(
                f"**{p.get('theme') or 'без темы'}** · отклик {p.get('engagement', 0):.0f} — "
                f"{(p.get('text') or '')[:120]}"
            )

    st.subheader("Выводы")
    st.caption("Если захочешь — соберу словами. Первый раз может подождать.")
    if st.button("сделать выводы", type="primary"):
        try:
            with st.spinner("Смотрю архив…"):
                report_data = api_get("/analytics", with_report=True)
            report = report_data.get("report")
            if report:
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
    st.caption("Идеи из архива. План — если сама захочешь, не каждый день.")

    st.subheader("Из архива к сезону")
    if st.button("показать сезонные", key="load_seasonal", type="secondary"):
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
                    if st.button("в план", key=f"arch_plan_{hit.get('post_id')}_{i}", type="secondary"):
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
                            st.session_state["_toast"] = "В плане"
                            st.rerun()
                        except Exception as exc:
                            friendly_error(exc)
                with b2:
                    if st.button("к черновику", key=f"arch_draft_{hit.get('post_id')}_{i}", type="secondary"):
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
        c1, c2 = st.columns([1, 2])
        with c1:
            count = st.slider("Сколько идей", 2, 6, 3)
        with c2:
            if st.button("предложить идеи", type="primary"):
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
                            st.session_state["_toast"] = "В плане"
                            st.rerun()
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
    item_id = item.get("id")
    with st.expander(f"{item.get('title')} · {label}"):
        status = st.selectbox(
            "Статус",
            _STATUS_ORDER,
            format_func=lambda s: _STATUS_LABEL.get(s, s),
            index=_safe_status_index(status_raw),
            key=f"status_{item_id}",
        )
        draft = st.text_area(
            "Черновик",
            value=item.get("draft_text") or "",
            key=f"draft_{item_id}",
            height=140,
        )
        st.markdown(char_counter(draft), unsafe_allow_html=True)
        raw_date = item.get("scheduled_date")
        date_default = date.fromisoformat(raw_date[:10]) if raw_date else date.today()
        date_val = st.date_input(
            "Дата",
            value=date_default,
            key=f"date_{item_id}",
            min_value=date.today() - timedelta(days=365),
        )
        col_save, col_text, col_del = st.columns([1.2, 1.4, 1])
        with col_save:
            if st.button("сохранить", key=f"save_plan_{item_id}", type="primary"):
                try:
                    api_patch(
                        f"/plan/{item_id}",
                        json={
                            "status": status,
                            "draft_text": draft,
                            "scheduled_date": date_val.isoformat() if date_val else None,
                        },
                    )
                    st.session_state["_toast"] = "Сохранено"
                    st.rerun()
                except Exception as exc:
                    friendly_error(exc)
        with col_text:
            if st.button("редактировать текст", key=f"to_text_{item_id}", type="secondary"):
                st.session_state["draft_from_idea"] = draft or item.get("title")
                st.session_state["plan_item_id"] = item_id
                save_desk()
                st.session_state["nav_to"] = "Текст"
                st.rerun()
        with col_del:
            if st.button("удалить", key=f"del_plan_{item_id}", type="secondary",
                         help="Удалить пункт плана безвозвратно"):
                try:
                    api_delete(f"/plan/{item_id}")
                    st.session_state["_toast"] = "Удалено из плана"
                    st.rerun()
                except Exception as exc:
                    friendly_error(exc)
        _publish_block(
            message=draft or item.get("title") or "",
            key_prefix=f"plan_pub_{item_id}",
            plan_item_id=item_id,
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
    st.caption("Если нужно — не обязанность.")
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
        empty_state("План пуст — добавь идею или импортируй из архива.")
        return

    monday, sunday = _week_bounds()
    today = date.today()
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
        is_today = day == today
        with cols[offset]:
            day_cls = "tr-day tr-day--today" if is_today else "tr-day"
            st.markdown(
                f'<div class="{day_cls}">{_WEEKDAYS_RU[offset]} · {day.strftime("%d.%m")}</div>',
                unsafe_allow_html=True,
            )
            if not items:
                st.caption("—")
            else:
                for item in items:
                    _plan_chip(item)

    # Мёртвая `editable` переменная убрана — ниже просто собираем список в логическом порядке
    if undated:
        st.markdown("##### Без даты")
        for item in undated:
            _render_plan_item(item)
    st.markdown("##### Правки")
    st.caption("Сетка сверху — обзор. Ниже можно менять статус, дату и черновик.")
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
    if st.button("обновить", key="inbox_refresh", type="secondary"):
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
                if st.button(label, key=f"inbox_pick_{row.get('peer_id')}_{i}", type="secondary", use_container_width=True):
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
    if st.button("черновик ответа", type="primary"):
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
    draft_text = reply.get("draft_reply") or ""
    out = st.text_area(
        "Черновик ответа",
        value=draft_text,
        height=180,
        key="concierge_draft_out",
    )
    if out:
        copy_to_clipboard_button(out, key="concierge_copy", label="копировать ответ")
    why_block(reply.get("why"))
    feedback_buttons(reply.get("suggestion_id"), "concierge")



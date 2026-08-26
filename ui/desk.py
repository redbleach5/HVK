"""Открытая вкладка и черновик — в профиле через API, не в JSON рядом."""

from __future__ import annotations

from typing import Any

import streamlit as st

from ui.api_client import api_get, api_patch, friendly_error

_DESK_TIMEOUT = 20.0


def load_desk() -> dict[str, Any]:
    data = api_get("/desk", timeout=_DESK_TIMEOUT)
    return data if isinstance(data, dict) else {}


def save_desk() -> None:
    body = {
        "desk": st.session_state.get("main_nav") or "Чат",
        "draft_text": st.session_state.get("current_draft") or "",
        "plan_item_id": st.session_state.get("plan_item_id"),
    }
    try:
        api_patch("/desk", json=body, timeout=_DESK_TIMEOUT)
    except Exception as exc:
        friendly_error(exc)

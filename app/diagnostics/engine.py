"""Самодиагностика: метрики, пробы, правила, краткий разбор моделью."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.metrics import latency_summary, recent_calls
from app.diagnostics.probes import json_path_probe
from app.llm.client import get_llm
from app.llm.exceptions import ModelAsleepError
from app.memory.store import MemoryStore
from app.schemas.common import DiagnosticsOut

logger = logging.getLogger(__name__)

_LAST_REPORT: dict[str, Any] | None = None

# пороги: чат быстрый, JSON-агенты тяжелее — но не «вечность»
_JSON_SLOW_MS = 180_000
_CHAT_SLOW_MS = 45_000
_JSON_FAIL_RATE = 0.35


def _author_hint(issues: list[str]) -> str | None:
    if not issues:
        return None
    if "archive_thin" in issues:
        return "Мало твоих текстов в памяти — идеи и сводки пока без опоры на архив."
    if "model_asleep" in issues:
        return "Редакция сейчас не отвечает — загляни чуть позже."
    if "json_path_slow" in issues and "chat_ok" in issues:
        return "Чат работает как обычно. Идеи и отчёты на столе могут идти дольше — это нормально."
    if "json_path_slow" in issues:
        return "Стол с идеями и аналитикой сейчас медленнее обычного."
    if "json_unstable" in issues:
        return "Иногда стол не собирает ответ с первого раза — можно повторить."
    return None


async def _maybe_insight(issues: list[str], snapshot: dict[str, Any]) -> str | None:
    if not issues:
        return None
    try:
        text = await get_llm().complete(
            system=(
                "Ты внутренний диагност ассистента блога. "
                "По метрикам назови 1–3 вероятные причины и одно действие для инженера. "
                "Кратко, русский, без портов и имён файлов."
            ),
            user=json.dumps({"issues": issues, "metrics": snapshot}, ensure_ascii=False),
            temperature=0.2,
            max_tokens=350,
            no_reasoning=True,
            label="diagnostics_insight",
        )
        return (text or "").strip()[:1200] or None
    except ModelAsleepError:
        return None
    except Exception:
        logger.debug("diagnostics insight skipped", exc_info=True)
        return None


async def run_diagnostics(
    session: AsyncSession,
    *,
    probe: bool = True,
    insight: bool = True,
) -> DiagnosticsOut:
    """Полный проход: архив, пинг, метрики, опционально JSON-проба и разбор."""
    global _LAST_REPORT
    memory = MemoryStore(session)
    llm = get_llm()
    brain = await llm.ping_brain()
    eyes = await llm.ping_eyes()
    posts = await memory.count_author_posts()
    voice = await memory.latest_voice()

    chat_lat = await latency_summary(kind="stream", label="chat")
    json_lat = await latency_summary(kind="complete_json")
    issues: list[str] = []
    checks: list[dict[str, Any]] = []

    checks.append({"id": "brain_ping", "ok": brain})
    checks.append({"id": "eyes_ping", "ok": eyes})
    checks.append({"id": "archive_posts", "ok": posts >= 2, "posts": posts})
    checks.append({"id": "voice_profile", "ok": voice is not None})
    try:
        from app.idle.worker import idle_status

        checks.append({"id": "idle_worker", **await idle_status()})
    except Exception:
        logger.debug("idle_status skipped", exc_info=True)

    if not brain:
        issues.append("model_asleep")
    if posts < 2:
        issues.append("archive_thin")

    chat_p95 = chat_lat.get("p95_ms")
    json_p95 = json_lat.get("p95_ms")
    json_n = int(json_lat.get("n") or 0)
    json_fail = int(json_lat.get("fail") or 0)

    if chat_p95 is not None and chat_p95 <= _CHAT_SLOW_MS:
        issues.append("chat_ok")
    if chat_p95 is not None and chat_p95 > _CHAT_SLOW_MS:
        issues.append("chat_slow")

    if json_p95 is not None and json_p95 > _JSON_SLOW_MS:
        issues.append("json_path_slow")
    if json_n >= 5 and json_fail / max(json_n, 1) >= _JSON_FAIL_RATE:
        issues.append("json_unstable")

    probe_result = None
    if probe and brain:
        probe_result = await json_path_probe(force=False)
        checks.append({"id": "json_probe", **probe_result})
        if not probe_result.get("skipped") and not probe_result.get("ok"):
            issues.append("json_probe_fail")
        if (
            not probe_result.get("skipped")
            and float(probe_result.get("duration_ms") or 0) > _JSON_SLOW_MS
        ):
            issues.append("json_path_slow")

    snapshot = {
        "chat_latency": chat_lat,
        "json_latency": json_lat,
        "probe": probe_result,
        "issues": issues,
    }

    ops_insight = await _maybe_insight(issues, snapshot) if insight and issues else None
    if ops_insight:
        checks.append({"id": "model_insight", "ok": True, "text": ops_insight})

    ok = brain and posts >= 2 and "json_unstable" not in issues and "model_asleep" not in issues
    report = DiagnosticsOut(
        ok=ok,
        checked_at=datetime.now(timezone.utc).isoformat(),
        author_hint=_author_hint(issues),
        issues=issues,
        checks=checks,
        chat_latency=chat_lat,
        json_latency=json_lat,
        recent_calls=await recent_calls(15),
        ops_insight=ops_insight,
    )
    _LAST_REPORT = report.model_dump()
    if issues:
        await memory.log(
            "diagnostics",
            f"Замечания: {', '.join(issues)}",
            {"issues": issues, "ops_insight": ops_insight},
        )
        logger.warning("Диагностика: %s", issues)
    else:
        logger.info("Диагностика: ok")
    return report


def last_report() -> dict[str, Any] | None:
    return _LAST_REPORT

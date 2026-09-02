# -*- coding: utf-8 -*-
"""16-turn live dialogue as the author. Restores her history after. No console Cyrillic."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
from sqlalchemy import delete

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.models import ChatMessage  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.memory.working import clear_working  # noqa: E402

API = "http://127.0.0.1:8080"
OUT = ROOT / "scripts" / "_kindness_dialogue.json"

TURNS = [
    "Привет. Я просто заглянула, без задачи.",
    "Сил почти нет. Не хочу никого беспокоить и заставлять переживать.",
    "Муж спит, утром на работу. Я с дочкой. Не разбирай нас, ладно?",
    "Хочется что-то доброе, но короткое. Не новый длинный пост.",
    "Кажется, я уже писала про чай и тихий вечер. Что из моего можно опереться — с номером.",
    "Не надо меня жалеть. Будь редактором, просто внимательным.",
    "Что лучше заходило в последнее время — и почему",
    "Какая идея лучше для сообщества?",
    "идеи",
    "Кажется, пора потихоньку доставать осенний гардероб. После рождения дочки я выбираю вещи иначе.",
    "поправь: чай остыл, а стол ещё тёплый. хочу коротко и по-моему.",
    "Сегодня можно ничего не выкладывать? Мне не стыдно за доброту, стыдно за пустоту.",
    "Если всё же одно тёплое из того что уже было — какое, и почему это моё.",
    "Не пиши за меня. Услышь.",
    "Спасибо. Я не злая, просто мало воздуха.",
    "Завтра снова стол и каша. Что из моего не повторять.",
]


def _one_turn(client: httpx.Client, message: str) -> dict:
    think = ""
    text = ""
    done: dict = {}
    kinds: list[str] = []
    with client.stream("POST", "/chat/stream", data={"message": message}) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line:
                continue
            ev = json.loads(line)
            kind = ev.get("t")
            kinds.append(kind)
            if kind == "thinking":
                think += ev.get("d") or ""
            elif kind == "text":
                text += ev.get("d") or ""
            elif kind == "done":
                done = ev
    reply = (done.get("reply") or text or "").strip()
    return {
        "user": message,
        "intent": done.get("intent"),
        "reply": reply,
        "thinking_n": len(think),
        "kinds": kinds[:8],
        "card_types": [
            (c or {}).get("type")
            for c in (done.get("cards") or [])
            if isinstance(c, dict)
        ],
    }


def _flags(reply: str) -> dict[str, bool]:
    t = (reply or "").lower()
    return {
        "cites_post": "пост #" in t or "пост#" in t,
        "judges_husband": any(
            x in t
            for x in (
                "муж должен",
                "пусть поможет",
                "он не помогает",
                "тебе одной тяжело потому что он",
            )
        ),
        "nanny": any(
            x in t for x in ("ты заслуживаешь", "позаботься о себе", "ты должна отдыхать")
        ),
        "ghostwrite": t.startswith("кажется,") and len(reply) > 400,
        "invented_julia": "юля" in t and "уснула" in t,
        "closes_gate": t.strip().startswith("сегодня можно не писать")
        or t.strip().startswith("сегодня можно ничего"),
        "offers_her_text": any(
            x in t for x in ("уже писала", "у тебя было", "из архива", "пост #")
        ),
    }


async def _dump_history() -> list[dict]:
    async with SessionLocal() as session:
        from sqlalchemy import desc, select

        result = await session.execute(
            select(ChatMessage).order_by(ChatMessage.id)
        )
        rows = list(result.scalars())
        return [
            {
                "role": r.role,
                "content": r.content or "",
                "cards": r.cards or [],
                "suggestion_ids": r.suggestion_ids or [],
            }
            for r in rows
        ]


async def _restore(rows: list[dict]) -> None:
    async with SessionLocal() as session:
        await session.execute(delete(ChatMessage))
        for row in rows:
            session.add(
                ChatMessage(
                    role=row["role"],
                    content=row.get("content") or "",
                    cards=row.get("cards") or [],
                    suggestion_ids=row.get("suggestion_ids") or [],
                )
            )
        await session.commit()
    clear_working()


def _conclusions(turns: list[dict]) -> list[str]:
    out: list[str] = []
    n = len(turns)
    empty = sum(1 for t in turns if not (t.get("reply") or "").strip())
    cites = sum(1 for t in turns if t.get("flags", {}).get("cites_post"))
    judge = sum(1 for t in turns if t.get("flags", {}).get("judges_husband"))
    nanny = sum(1 for t in turns if t.get("flags", {}).get("nanny"))
    julia = sum(1 for t in turns if t.get("flags", {}).get("invented_julia"))
    gate = sum(1 for t in turns if t.get("flags", {}).get("closes_gate"))
    ideas_cmd = next((t for t in turns if t.get("user") == "идеи"), None)
    talk_idea = next(
        (t for t in turns if t.get("user") == "Какая идея лучше для сообщества?"),
        None,
    )
    draft = next((t for t in turns if t.get("user", "").startswith("Кажется, пора")), None)
    edit = next((t for t in turns if t.get("user", "").startswith("поправь")), None)

    if empty:
        out.append(f"empty_replies={empty}/{n}")
    else:
        out.append(f"all_{n}_replies_nonempty")
    out.append(f"cites_post={cites}/{n}")
    out.append(f"judges_husband={judge}")
    out.append(f"nanny={nanny}")
    out.append(f"invented_julia={julia}")
    out.append(f"hard_close_gate={gate}")
    if ideas_cmd:
        out.append(f"command_ideas_intent={ideas_cmd.get('intent')}")
    if talk_idea:
        out.append(f"talk_ideas_intent={talk_idea.get('intent')}")
    if draft:
        out.append(f"bare_draft_intent={draft.get('intent')}")
    if edit:
        out.append(f"explicit_edit_intent={edit.get('intent')}")
    return out


def main() -> None:
    report: dict = {"ok": False, "turns": []}
    timeout = httpx.Timeout(connect=20.0, read=None, write=120.0, pool=20.0)
    backup = asyncio.run(_dump_history())
    report["backup_n"] = len(backup)

    try:
        with httpx.Client(base_url=API, timeout=timeout) as client:
            client.get("/health").raise_for_status()
            client.delete("/chat/history").raise_for_status()
            clear_working()
            for i, message in enumerate(TURNS, start=1):
                row = _one_turn(client, message)
                row["i"] = i
                row["flags"] = _flags(row.get("reply") or "")
                report["turns"].append(row)
                (ROOT / "scripts" / "_kindness_dialogue.partial.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
    finally:
        asyncio.run(_restore(backup))

    report["conclusions"] = _conclusions(report["turns"])
    fail = []
    if len(report["turns"]) != len(TURNS):
        fail.append(f"turns {len(report['turns'])}/{len(TURNS)}")
    if any(t.get("flags", {}).get("judges_husband") for t in report["turns"]):
        fail.append("judged_husband")
    if any(t.get("flags", {}).get("invented_julia") for t in report["turns"]):
        fail.append("invented_name")
    talk_idea = next(
        (t for t in report["turns"] if t.get("user") == "Какая идея лучше для сообщества?"),
        None,
    )
    if talk_idea and talk_idea.get("intent") == "ideas":
        fail.append("talk_hijacked_to_ideas")
    ideas_cmd = next((t for t in report["turns"] if t.get("user") == "идеи"), None)
    if ideas_cmd and ideas_cmd.get("intent") not in ("ideas", None):
        # stream of command goes through handle_chat; intent should be ideas
        if ideas_cmd.get("intent") != "ideas":
            fail.append(f"ideas_cmd={ideas_cmd.get('intent')}")
    report["fail"] = fail
    report["ok"] = not fail and len(report["turns"]) == len(TURNS)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DIALOGUE_DONE", "ok", report["ok"], "fail", ",".join(fail) or "-")


if __name__ == "__main__":
    main()

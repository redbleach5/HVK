# -*- coding: utf-8 -*-
"""Screenshot Streamlit after the websocket UI is actually painted."""
from __future__ import annotations

import asyncio
import base64
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

try:
    from websockets.asyncio.client import connect as ws_connect
except ImportError:
    from websockets import connect as ws_connect  # type: ignore

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
SHOTS = Path(r"C:\HVK\scripts\_shots")
DEBUG_PORT = 9333


async def _cdp(ws, mid: int, method: str, params: dict | None = None) -> dict:
    await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    while True:
        raw = await ws.recv()
        msg = json.loads(raw)
        if msg.get("id") == mid:
            return msg


async def shot(
    name: str,
    url: str,
    needle: str,
    timeout_s: float = 25.0,
    *,
    click: str = "",
) -> dict:
    SHOTS.mkdir(parents=True, exist_ok=True)
    png = SHOTS / f"{name}.png"
    profile = Path(tempfile.mkdtemp(prefix=f"hvk_cdp_{name}_"))
    proc = subprocess.Popen(
        [
            str(CHROME),
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--no-first-run",
            f"--remote-debugging-port={DEBUG_PORT}",
            f"--user-data-dir={profile}",
            "--window-size=1400,2200",
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    ws_url = ""
    try:
        for _ in range(40):
            try:
                tabs = httpx.get(f"http://127.0.0.1:{DEBUG_PORT}/json", timeout=1.0).json()
                page = next((t for t in tabs if t.get("type") == "page"), tabs[0] if tabs else None)
                if page and page.get("webSocketDebuggerUrl"):
                    ws_url = page["webSocketDebuggerUrl"]
                    break
            except Exception:
                pass
            await asyncio.sleep(0.25)
        if not ws_url:
            return {"name": name, "error": "no cdp tab"}
        async with ws_connect(ws_url, max_size=20_000_000) as ws:
            await _cdp(ws, 1, "Page.enable")
            await _cdp(ws, 2, "Runtime.enable")
            text = ""
            clicked = not click
            steps = int(timeout_s / 0.5)
            for i in range(steps):
                if click and not clicked:
                    clk = await _cdp(
                        ws,
                        400 + i,
                        "Runtime.evaluate",
                        {
                            "expression": (
                                "(() => { const t = %s; const b = [...document.querySelectorAll('button')]"
                                ".find(el => (el.innerText || '').trim() === t); if (b) { b.click(); return true; }"
                                " return false; })()"
                            )
                            % json.dumps(click),
                            "returnByValue": True,
                        },
                    )
                    clicked = bool(
                        ((clk.get("result") or {}).get("result") or {}).get("value")
                    )
                    if clicked:
                        await asyncio.sleep(1.2)
                msg = await _cdp(
                    ws,
                    10 + i,
                    "Runtime.evaluate",
                    {
                        "expression": "document.body ? document.body.innerText : ''",
                        "returnByValue": True,
                    },
                )
                text = (
                    ((msg.get("result") or {}).get("result") or {}).get("value") or ""
                )
                if needle in text and "Please wait" not in text:
                    await asyncio.sleep(0.8)
                    break
                await asyncio.sleep(0.5)
            cap = await _cdp(ws, 900, "Page.captureScreenshot", {"format": "png", "fromSurface": True})
            data = ((cap.get("result") or {}).get("data")) or ""
            if data:
                png.write_bytes(base64.b64decode(data))
            return {
                "name": name,
                "png_bytes": png.stat().st_size if png.exists() else 0,
                "has_needle": needle in text,
                "text_sample": text[:400].replace("\n", " | "),
            }
    finally:
        proc.kill()
        proc.wait(timeout=5)
        shutil.rmtree(profile, ignore_errors=True)


async def main() -> None:
    home = "http://127.0.0.1:8501/"
    pages = [
        ("chat", "", "Напиши сообщение"),
        ("today", "Сегодня", "Сводка, идеи и план"),
        ("photo", "Фото", "Загрузи кадр"),
    ]
    original = {}
    out: list = []
    with httpx.Client(base_url="http://127.0.0.1:8080", timeout=20.0) as client:
        original = client.get("/desk").json()
        try:
            for name, click, needle in pages:
                out.append(await shot(name, home, needle, click=click))
        finally:
            client.patch(
                "/desk",
                json={
                    "desk": "Чат",
                    "draft_text": original.get("draft_text") or "",
                    "plan_item_id": original.get("plan_item_id"),
                },
            )
    Path(r"C:\HVK\scripts\_shots\report.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    asyncio.run(main())

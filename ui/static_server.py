"""Раздача React SPA на :8501 + прокси API на :8080."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
API_BASE = "http://127.0.0.1:8080"

app = FastAPI(title="Тихая редакция UI")

_STREAM_PATHS = frozenset({"chat/stream"})
_STREAM_TYPES = ("application/x-ndjson", "text/event-stream")
_TIMEOUT = httpx.Timeout(1200.0, connect=20.0)


def _proxy_headers(request: Request) -> dict[str, str]:
    return {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length", "connection")
    }


def _response_headers(headers: httpx.Headers) -> dict[str, str]:
    return {
        k: v
        for k, v in headers.items()
        if k.lower() not in ("content-encoding", "transfer-encoding", "connection", "content-length")
    }


def _wants_stream(path: str, content_type: str | None) -> bool:
    if path in _STREAM_PATHS:
        return True
    if not content_type:
        return False
    low = content_type.lower()
    return any(token in low for token in _STREAM_TYPES)


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_api(request: Request, path: str) -> Response:
    """Проксирует /api/* на FastAPI :8080. Стрим чата — без буферизации."""
    url = f"{API_BASE}/{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"
    body = await request.body()
    headers = _proxy_headers(request)

    if path in _STREAM_PATHS:
        client = httpx.AsyncClient(timeout=_TIMEOUT)
        req = client.build_request(request.method, url, content=body, headers=headers)
        upstream = await client.send(req, stream=True)

        async def stream_body() -> AsyncIterator[bytes]:
            try:
                async for chunk in upstream.aiter_bytes():
                    yield chunk
            finally:
                await upstream.aclose()
                await client.aclose()

        out_headers = _response_headers(upstream.headers)
        out_headers.setdefault("Cache-Control", "no-cache")
        out_headers.setdefault("X-Accel-Buffering", "no")
        return StreamingResponse(
            stream_body(),
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "application/x-ndjson"),
            headers=out_headers,
        )

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        async with client.stream(request.method, url, content=body, headers=headers) as upstream:
            content_type = upstream.headers.get("content-type")
            if _wants_stream(path, content_type):

                async def passthrough() -> AsyncIterator[bytes]:
                    async for chunk in upstream.aiter_bytes():
                        yield chunk

                return StreamingResponse(
                    passthrough(),
                    status_code=upstream.status_code,
                    headers=_response_headers(upstream.headers),
                    media_type=content_type,
                )

            data = await upstream.aread()
            return Response(
                content=data,
                status_code=upstream.status_code,
                headers=_response_headers(upstream.headers),
                media_type=content_type,
            )


if DIST.is_dir():

    @app.get("/{rest:path}")
    async def spa(rest: str = "") -> Response:
        """SPA fallback: deep links вроде /desk/today отдают index.html."""
        if rest:
            candidate = DIST / rest
            if candidate.is_file():
                return FileResponse(candidate)
        index = DIST / "index.html"
        if not index.is_file():
            return Response(status_code=404)
        return FileResponse(index)

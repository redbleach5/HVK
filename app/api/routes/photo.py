"""Фото-анализ."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.photo import analyze_photos
from app.config import get_settings
from app.db.session import get_session
from app.schemas.agents import PhotoAnalysis

router = APIRouter(prefix="/photo", tags=["photo"])


@router.post("/analyze", response_model=PhotoAnalysis)
async def photo_analyze(
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_session),
) -> PhotoAnalysis:
    """Принимает одно или несколько фото и возвращает вердикт."""
    settings = get_settings()
    upload_dir = settings.resolve_path(settings.uploads_path)
    upload_dir.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    for upload in files:
        suffix = Path(upload.filename or "photo.jpg").suffix or ".jpg"
        dest = upload_dir / f"{uuid.uuid4().hex}{suffix}"
        data = await upload.read()
        dest.write_bytes(data)
        paths.append(dest)

    return await analyze_photos(session, paths)

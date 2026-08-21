"""HTTP-роуты приложения."""

from app.api.routes import health, ideas_plan, misc, onboarding, photo, text, today

__all__ = ["health", "onboarding", "today", "photo", "text", "ideas_plan", "misc"]

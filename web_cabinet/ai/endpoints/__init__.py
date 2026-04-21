"""AI endpoints — регистрация маршрутов в FastAPI app."""
from __future__ import annotations

from fastapi import FastAPI

from ..config import get_ai_settings


def register_ai_routes(app: FastAPI) -> None:
    from .health import router as health_router
    app.include_router(health_router, prefix="/api/ai", tags=["ai"])

"""AI endpoints — регистрация маршрутов в FastAPI app."""
from __future__ import annotations

from fastapi import FastAPI

from ..config import get_ai_settings


def register_ai_routes(app: FastAPI) -> None:
    from .health import router as health_router
    from .morning_brief import router as morning_brief_router
    from .morning_brief_pdf import router as morning_brief_pdf_router
    from .ask_farm import router as ask_farm_router

    app.include_router(health_router, prefix="/api/ai", tags=["ai"])
    app.include_router(morning_brief_router, prefix="/api/ai", tags=["ai-morning-brief"])
    app.include_router(morning_brief_pdf_router, prefix="/api/ai", tags=["ai-morning-brief"])
    app.include_router(ask_farm_router, prefix="/api/ai", tags=["ai"])

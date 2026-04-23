"""AI health endpoint — /api/ai/health."""
from __future__ import annotations

from fastapi import APIRouter

from ..config import get_ai_settings
from ..models import AIHealthResponse

router = APIRouter()


@router.get("/health", response_model=AIHealthResponse)
def ai_health() -> AIHealthResponse:
    """Smoke-check: AI gateway работает, модель настроена."""
    settings = get_ai_settings()
    return AIHealthResponse(
        status="ok",
        model=settings.GENOMEAI_AI_DEFAULT_MODEL,
        demo_mode=settings.GENOMEAI_AI_DEMO_MODE,
        cache_enabled=settings.GENOMEAI_AI_ENABLE_CACHE,
        api_configured=settings.is_configured,
    )

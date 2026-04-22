"""Конфигурация AI-gateway через pydantic-settings (читает .env.ai)."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel, field_validator

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
    _HAS_PYDANTIC_SETTINGS = True
except ImportError:
    _HAS_PYDANTIC_SETTINGS = False


class _AISettingsBase(BaseModel):
    ANTHROPIC_API_KEY: str = ""
    GENOMEAI_AI_DEFAULT_MODEL: str = "claude-sonnet-4-6"
    GENOMEAI_AI_OPUS_MODEL: str = "claude-opus-4-7"
    GENOMEAI_AI_HAIKU_MODEL: str = "claude-haiku-4-5"
    # CSV-строки — парсятся в list через свойства
    GENOMEAI_AI_USE_OPUS_FOR: str = "morning_brief,weekly_brief"
    GENOMEAI_AI_ENABLE_CACHE: bool = True
    GENOMEAI_AI_CACHE_TTL_SECONDS: int = 300
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    GENOMEAI_AI_RATE_LIMIT_PER_MIN: int = 60
    GENOMEAI_AI_RATE_LIMIT_PER_HOUR: int = 500
    GENOMEAI_AI_GLOBAL_RATE_LIMIT_PER_HOUR: int = 2000
    GENOMEAI_AI_MONTHLY_BUDGET_USD: float = 50.0
    GENOMEAI_AI_DEMO_MODE: bool = True
    GENOMEAI_AI_DEMO_PRESET_QUESTIONS: str = "why_star_milk_drop,which_to_cull,cows_in_heat_today"
    GENOMEAI_AI_LOG_LEVEL: str = "INFO"
    GENOMEAI_AI_LOG_FORMAT: str = "json"
    GENOMEAI_AI_LOG_PATH: str = "/var/log/genomeai-ai/ai-gateway.log"
    GENOMEAI_TIMEZONE: str = "Europe/Moscow"
    GENOMEAI_DEMO_FARM_ID: str = "demo-farm-v1"
    GENOMEAI_AI_ASSISTANT_NAME: str = "ИИ-помощник"
    GENOMEAI_AI_MORNING_BRIEF_CRON: str = "0 6 * * *"
    GENOMEAI_AI_INSIGHT_SCANNER_CRON: str = "0 */6 * * *"
    GENOMEAI_AI_WEEKLY_BRIEF_CRON: str = "0 7 * * 1"

    @property
    def use_opus_for(self) -> list[str]:
        return [s.strip() for s in self.GENOMEAI_AI_USE_OPUS_FOR.split(",") if s.strip()]

    @property
    def demo_preset_questions(self) -> list[str]:
        return [s.strip() for s in self.GENOMEAI_AI_DEMO_PRESET_QUESTIONS.split(",") if s.strip()]

    def model_for_task(self, task_type: str) -> str:
        """Возвращает модель в зависимости от типа задачи."""
        if task_type in self.use_opus_for:
            return self.GENOMEAI_AI_OPUS_MODEL
        return self.GENOMEAI_AI_DEFAULT_MODEL

    @property
    def is_configured(self) -> bool:
        return bool(self.ANTHROPIC_API_KEY) and not self.ANTHROPIC_API_KEY.startswith("sk-ant-api03-ВСТАВЬ")


if _HAS_PYDANTIC_SETTINGS:
    class AISettings(_AISettingsBase, BaseSettings):  # type: ignore[misc]
        model_config = SettingsConfigDict(
            env_file=".env.ai",
            env_file_encoding="utf-8",
            extra="ignore",
        )
else:
    import os

    class AISettings(_AISettingsBase):  # type: ignore[no-redef]
        @classmethod
        def from_env(cls) -> "AISettings":
            data = {k: os.environ[k] for k in cls.model_fields if k in os.environ}
            return cls(**data)


@lru_cache(maxsize=1)
def get_ai_settings() -> AISettings:
    return AISettings()

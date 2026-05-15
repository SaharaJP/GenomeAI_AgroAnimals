"""LLM provider health (P1-6).

Reports a single row for the active LLM provider. We do NOT ping the
upstream (that would burn $$ on every admin page open). Status is based
purely on whether credentials are configured:
  - ok        — OPENAI_API_KEY is configured (or file mount exists)
  - disabled  — no credentials; UI shows "не настроено"

P2-2 (Ollama migration) will extend this with a real /api/tags call.
"""
from __future__ import annotations

import os
from typing import Any

from packages.contracts.integrations_health_v1 import IntegrationHealth


def _has_openai_key() -> bool:
    if (os.environ.get('OPENAI_API_KEY') or '').strip():
        return True
    file_env = (os.environ.get('OPENAI_API_KEY_FILE') or '').strip()
    if file_env and os.path.exists(file_env):
        try:
            with open(file_env, 'r', encoding='utf-8') as f:
                return bool(f.read().strip())
        except OSError:
            return False
    return False


class LLMHealthProvider:
    """One row representing the LLM provider."""

    def get_health(self, conn: Any, *, tenant_id: str = 'default') -> list[IntegrationHealth]:
        provider = (os.environ.get('GENOMEAI_LLM_PROVIDER') or 'openai').strip().lower()
        configured = _has_openai_key() if provider in ('openai', '') else True
        if not configured:
            return [
                IntegrationHealth(
                    id=f'llm.{provider}',
                    name=f'LLM provider ({provider})',
                    kind='llm',
                    status='disabled',
                    note='Не настроено: установите OPENAI_API_KEY или OPENAI_API_KEY_FILE.',
                )
            ]
        return [
            IntegrationHealth(
                id=f'llm.{provider}',
                name=f'LLM provider ({provider})',
                kind='llm',
                status='ok',
                note='Учётные данные сконфигурированы. Реальный ping появится в P2-2 (Ollama).',
            )
        ]


__all__ = ['LLMHealthProvider']

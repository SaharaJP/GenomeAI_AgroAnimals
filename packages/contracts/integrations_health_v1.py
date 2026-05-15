"""Public contract for /api/app/v1/integrations/health (P1-6).

One row per source-system. Provider implementations live in
`src/core/interoperability/providers/`. Frontend mirror is at
`web_app/lib/api/integrations.ts`.

Statuses are intentionally bounded:
  - ok        — last attempt succeeded and is fresh
  - degraded  — succeeded but with lag/partial errors
  - down      — last attempt failed or unreachable
  - disabled  — integration exists in catalog but is not turned on
                (covers stubs awaiting P2-3 / P2-4 work)
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


IntegrationStatus = Literal['ok', 'degraded', 'down', 'disabled']

IntegrationKind = Literal[
    'llm',
    'batch_connector',
    'iot_device',
    'external_system',
    'sensor_ingestion',
]


class IntegrationHealth(BaseModel):
    """Health snapshot for one integration row.

    `id` is a stable opaque key (e.g. 'llm.openai', 'batch.selex',
    'iot.collar'); UI uses it for de-dup / per-row expand.
    """

    model_config = ConfigDict(extra='forbid')

    id: str
    name: str
    kind: IntegrationKind
    status: IntegrationStatus
    last_sync_at: Optional[str] = None
    records_in_last_window: Optional[int] = None
    error_count: Optional[int] = None
    last_error: Optional[str] = None
    latency_ms: Optional[int] = None
    note: Optional[str] = None


class IntegrationsHealthResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    schema_version: str = Field(
        default='genomeai.api.integrations.health.v1',
        serialization_alias='schema',
    )
    items: list[IntegrationHealth] = Field(default_factory=list)
    total: int = 0


__all__ = [
    'IntegrationHealth',
    'IntegrationKind',
    'IntegrationStatus',
    'IntegrationsHealthResponse',
]

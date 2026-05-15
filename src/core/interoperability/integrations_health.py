"""Provider protocol and registry for /integrations/health (P1-6).

Concrete providers live in `src/core/interoperability/providers/`. Each
provider implements `get_health(conn) -> list[IntegrationHealth]` and is
registered at module import time via `register_provider`.

The aggregator endpoint iterates registered providers, captures any
exceptions per-provider (so one bad provider doesn't break the whole
catalog), and returns a flat list.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Protocol, runtime_checkable

from packages.contracts.integrations_health_v1 import IntegrationHealth

logger = logging.getLogger(__name__)


@runtime_checkable
class IntegrationHealthProvider(Protocol):
    """Anything that can report one or more integration rows.

    Providers MUST be cheap to call — health endpoint runs them on each
    GET. If a provider needs network I/O (e.g. live LLM ping), it should
    return a cached snapshot and refresh asynchronously.

    `tenant_id` is the caller's tenant; providers that read per-tenant
    state (e.g. connector_runs) must use it instead of hardcoded
    'default'. Providers that are tenant-agnostic (LLM env vars, IoT
    catalogue stubs) may safely ignore it.
    """

    def get_health(self, conn: Any, *, tenant_id: str = 'default') -> list[IntegrationHealth]:
        ...


_REGISTRY: list[IntegrationHealthProvider] = []


def register_provider(provider: IntegrationHealthProvider) -> None:
    """Idempotent registration — same instance is added at most once."""
    if provider not in _REGISTRY:
        _REGISTRY.append(provider)


def iter_providers() -> list[IntegrationHealthProvider]:
    return list(_REGISTRY)


def reset_registry() -> None:
    """Test-only helper. Production code never calls this."""
    _REGISTRY.clear()


def collect_health(conn: Any, *, tenant_id: str = 'default') -> list[IntegrationHealth]:
    """Run every registered provider and concatenate the rows.

    Provider failures are logged and yield a synthetic `down` row so the
    operator sees that something is broken instead of the whole endpoint
    falling over.
    """
    out: list[IntegrationHealth] = []
    for provider in iter_providers():
        provider_name = type(provider).__name__
        try:
            rows = provider.get_health(conn, tenant_id=tenant_id) or []
        except Exception as exc:
            logger.exception('integrations.health.provider_failed name=%s', provider_name)
            out.append(
                IntegrationHealth(
                    id=f'_error.{provider_name}',
                    name=f'Provider error: {provider_name}',
                    kind='external_system',
                    status='down',
                    last_error=str(exc)[:200],
                )
            )
            continue
        out.extend(rows)
    return out


__all__ = [
    'IntegrationHealthProvider',
    'collect_health',
    'iter_providers',
    'register_provider',
    'reset_registry',
]

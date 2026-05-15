"""External RU systems stub provider (P1-6).

Only Хэрриот appears here — Селекс и 1С уже представлены через
connectors_v1 (batch CSV pipeline), и одна row per system отображается
там, с note про upcoming P2-4 upgrade.

Хэрриот (ФГИС ВетИС / Меркурий) — нет batch-уровня; live API только в
P2-4 (дорожка C), требует сертификатов УЦ Россельхознадзора.
"""
from __future__ import annotations

from typing import Any

from packages.contracts.integrations_health_v1 import IntegrationHealth


class RuExternalSystemsStubProvider:
    def get_health(self, conn: Any, *, tenant_id: str = 'default') -> list[IntegrationHealth]:
        return [
            IntegrationHealth(
                id='external.herriot',
                name='Хэрриот (ФГИС ВетИС)',
                kind='external_system',
                status='disabled',
                note=(
                    'Запланировано в P2-4 (дорожка C). Требует сертификатов УЦ '
                    'Россельхознадзора и отдельного RFC по регуляторике.'
                ),
            )
        ]


__all__ = ['RuExternalSystemsStubProvider']

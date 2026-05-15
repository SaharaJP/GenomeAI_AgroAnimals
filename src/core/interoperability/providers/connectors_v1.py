"""Batch connector framework health (P1-6).

One row per `source_system` known to the platform. Sources are taken from
two places:
  1. Active configs in `configs/connectors/*.yaml`.
  2. Catalog blueprints in `configs/connector_catalog/*.yaml` that don't
     yet have an active config — they appear with status='disabled' so the
     operator sees the system in the catalog and can plan activation.

For active connectors we look up the latest `connector_runs` row and map
its status to {ok, degraded, down}.

P2-4 will upgrade Селекс/1С/Хэрриот from this batch layer to live API
integrations — for those systems we include a `note` hinting at the
upcoming upgrade.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from core.infra.repositories import ConnectorRunsRepo
from packages.contracts.integrations_health_v1 import IntegrationHealth


_PROJECT_ROOT = Path(__file__).resolve().parents[4]


_P2_4_NOTES = {
    'Селекс': 'Сейчас batch CSV pipeline. Live API в P2-4 (дорожка A).',
    'Selex': 'Сейчас batch CSV pipeline. Live API в P2-4 (дорожка A).',
    '1С:Зоотехния': 'Сейчас batch CSV pipeline. REST/OData в P2-4 (дорожка B).',
    '1C': 'Сейчас batch CSV pipeline. REST/OData в P2-4 (дорожка B).',
    'DairyComp 305': 'Batch CSV pipeline (blueprint).',
}


def _safe_load_yaml(path: Path) -> Optional[dict]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else None
    except OSError:
        return None
    except yaml.YAMLError:
        return None


def _scan_dir(dirpath: Path) -> list[dict]:
    if not dirpath.is_dir():
        return []
    out: list[dict] = []
    for path in sorted(dirpath.glob('*.yaml')):
        data = _safe_load_yaml(path)
        if data:
            data['_config_path'] = str(path.relative_to(_PROJECT_ROOT))
            out.append(data)
    return out


def _status_from_run(run: dict) -> str:
    raw = (run.get('status') or '').lower().strip()
    if raw == 'success':
        return 'ok'
    if raw == 'partial':
        return 'degraded'
    if raw in ('failed', 'error'):
        return 'down'
    if raw in ('noop', 'stub'):
        return 'disabled'
    return 'disabled'


class ConnectorsV1HealthProvider:
    """Aggregates `source_system` rows from connectors_v1 framework."""

    def get_health(self, conn: Any, *, tenant_id: str = 'default') -> list[IntegrationHealth]:
        active = _scan_dir(_PROJECT_ROOT / 'configs' / 'connectors')
        blueprints = _scan_dir(_PROJECT_ROOT / 'configs' / 'connector_catalog')

        # Group: source_system → first active config (if any), else blueprint
        by_system: dict[str, dict] = {}
        for cfg in active:
            sys = str(cfg.get('source_system') or cfg.get('connector_id') or 'unknown')
            by_system.setdefault(sys, {'config': cfg, 'from_active': True})
        for bp in blueprints:
            sys = str(bp.get('source_system') or bp.get('catalog_id') or 'unknown')
            by_system.setdefault(sys, {'config': bp, 'from_active': False})

        rows: list[IntegrationHealth] = []
        repo: Optional[ConnectorRunsRepo]
        try:
            repo = ConnectorRunsRepo(conn)
        except Exception:
            repo = None

        for sys, entry in sorted(by_system.items()):
            cfg = entry['config']
            connector_id = str(cfg.get('connector_id') or cfg.get('catalog_id') or sys)
            note = _P2_4_NOTES.get(sys)

            latest: Optional[dict] = None
            if entry['from_active'] and repo is not None:
                try:
                    runs = repo.list_runs(tenant_id=tenant_id, connector_id=connector_id, limit=1) or []
                    latest = runs[0] if runs else None
                except Exception:
                    latest = None

            if latest is None and not entry['from_active']:
                rows.append(
                    IntegrationHealth(
                        id=f'batch.{connector_id}',
                        name=sys,
                        kind='batch_connector',
                        status='disabled',
                        note=note or 'Blueprint доступен, активной конфигурации нет.',
                    )
                )
                continue

            if latest is None:
                rows.append(
                    IntegrationHealth(
                        id=f'batch.{connector_id}',
                        name=sys,
                        kind='batch_connector',
                        status='disabled',
                        note=note or 'Конфигурация активна, но прогонов пока не было.',
                    )
                )
                continue

            rows.append(
                IntegrationHealth(
                    id=f'batch.{connector_id}',
                    name=sys,
                    kind='batch_connector',
                    status=_status_from_run(latest),
                    last_sync_at=latest.get('finished_at') or latest.get('started_at'),
                    last_error=(latest.get('error_text') or latest.get('message') or None) if _status_from_run(latest) != 'ok' else None,
                    note=note,
                )
            )
        return rows


__all__ = ['ConnectorsV1HealthProvider']

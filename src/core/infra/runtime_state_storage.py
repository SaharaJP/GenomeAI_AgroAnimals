from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Optional

try:  # pragma: no cover - optional dependency in local/test compat env
    import psycopg  # type: ignore
    from psycopg.rows import dict_row  # type: ignore
except Exception:  # pragma: no cover
    psycopg = None
    dict_row = None

from core.infra.runtime_storage import (
    RuntimeStorageConfigError,
    resolve_runtime_storage_settings,
    runtime_storage_diagnostics,
)
from core.infra.web_db import get_settings


RUNTIME_STATE_ENTITIES: tuple[str, ...] = (
    'jobs',
    'audit_log',
    'alerts_v2',
    'tasks_v1',
    'decision_log_v2',
    'connector_runs',
    'saved_views_v1',
    'favorites_v1',
    'report_templates_v1',
    'report_approvals_v1',
    'whatif_scenarios_v1',
    'whatif_reports_v1',
)

LEGACY_SQLITE_TABLES = {
    'jobs',
    'audit_log',
    'alerts_v2',
    'tasks_v1',
    'decision_log_v2',
    'connector_runs',
    'saved_views_v1',
    'favorites_v1',
    'report_templates_v1',
    'report_approvals_v1',
    'whatif_scenarios_v1',
    'whatif_reports_v1',
}

ENTITY_INDEX_HINTS: dict[str, tuple[str, ...]] = {
    'jobs': ('status, created_at DESC', 'run_id', 'data_version'),
    'audit_log': ('tenant_id, ts DESC', 'tenant_id, action, ts DESC', 'tenant_id, object_type, object_id, ts DESC'),
    'alerts_v2': ('tenant_id, status', 'alert_type', 'tenant_id, object_type, object_id'),
    'tasks_v1': ('tenant_id, status', 'tenant_id, due_at', 'tenant_id, linked_decision_id'),
    'decision_log_v2': ('tenant_id, created_at DESC', 'tenant_id, object_type, object_id', 'tenant_id, related_alert'),
    'connector_runs': ('tenant_id, connector_id, started_at DESC', 'status, started_at DESC'),
    'saved_views_v1': ('tenant_id, page_key', 'tenant_id, created_by'),
    'favorites_v1': ('tenant_id, user_id', 'object_type, object_id'),
    'report_templates_v1': ('tenant_id, created_by',),
    'report_approvals_v1': ('tenant_id, data_version', 'tenant_id, status'),
    'whatif_scenarios_v1': ('tenant_id, status', 'tenant_id, created_at DESC', 'tenant_id, approved_at DESC'),
    'whatif_reports_v1': ('tenant_id, scenario_id', 'tenant_id, created_at DESC'),
}

ENTITY_RETENTION_NOTES: dict[str, str] = {
    'jobs': 'keep recent operational window; archive finished/cancelled rows by retention policy, preserve lineage columns',
    'audit_log': 'append-only; archive by tenant/cutoff, never hard-delete privileged history in normal ops',
    'alerts_v2': 'resolved alerts may be archived after operational SLA window, keep decision linkage',
    'tasks_v1': 'done/cancelled tasks may be archived after evidence window, keep outcome linkage',
    'decision_log_v2': 'append-only operational governance history; keep long-term',
    'connector_runs': 'retain enough runs for SLA/debug trending; archive older success/noop rows',
    'saved_views_v1': 'user/shared UX state; low-risk retention cleanup allowed',
    'favorites_v1': 'user UX state; low-risk retention cleanup allowed',
    'report_templates_v1': 'retain active/shared templates; soft archive preferred',
    'report_approvals_v1': 'retain approvals tied to report lineage and audit',
    'whatif_scenarios_v1': 'retain approved/archived scenarios with who/when evidence',
    'whatif_reports_v1': 'retain published what-if report metadata with scenario linkage',
}


@dataclass(frozen=True)
class RuntimeStateEntityStatus:
    entity: str
    backend: str
    primary_state: bool
    legacy_sqlite_primary: bool
    migrated: bool
    count: int | None
    index_hints: tuple[str, ...]
    retention_note: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RuntimeStateDiagnostics:
    backend: str
    profile: str
    adult_mode: bool
    compat_mode: bool
    migration_status: str
    primary_runtime_state_backend: str
    support_bundle_legacy_web_db_default: bool
    restore_legacy_web_db_default: bool
    maintenance_notes: dict[str, Any]
    entities: tuple[RuntimeStateEntityStatus, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['entities'] = [item.as_dict() for item in self.entities]
        return payload


class SqliteCompatRuntimeStateStorage:
    backend = 'sqlite'

    def __init__(self, *, db_path: str | Path):
        self.db_path = Path(db_path).resolve()

    def diagnostics(self) -> RuntimeStateDiagnostics:
        counts: dict[str, int] = {entity: 0 for entity in RUNTIME_STATE_ENTITIES}
        settings = get_settings()
        runtime = runtime_storage_diagnostics(
            resolve_runtime_storage_settings(
                project_root=settings.project_root,
                storage_dir=settings.storage_dir,
                sqlite_db_path=settings.db_path,
            )
        )
        entities = tuple(
            RuntimeStateEntityStatus(
                entity=entity,
                backend='sqlite',
                primary_state=True,
                legacy_sqlite_primary=True,
                migrated=False,
                count=counts.get(entity),
                index_hints=ENTITY_INDEX_HINTS.get(entity, ()),
                retention_note=ENTITY_RETENTION_NOTES.get(entity, ''),
            )
            for entity in RUNTIME_STATE_ENTITIES
        )
        return RuntimeStateDiagnostics(
            backend='sqlite',
            profile=str(runtime.profile),
            adult_mode=bool(runtime.adult_mode),
            compat_mode=bool(runtime.compat_mode),
            migration_status='sqlite_compat_runtime_state',
            primary_runtime_state_backend='sqlite',
            support_bundle_legacy_web_db_default=True,
            restore_legacy_web_db_default=True,
            maintenance_notes={
                'vacuum_guidance': 'VACUUM/ANALYZE remain relevant for sqlite compat only.',
                'recovery_model': 'sqlite compat path is recovery-friendly for local/dev/test, not adult runtime proof.',
            },
            entities=entities,
        )


class PostgresRuntimeStateStorage:
    backend = 'postgres'

    def __init__(self, *, dsn: str, connection_factory: Callable[[], Any] | None = None):
        self.dsn = str(dsn or '').strip()
        self._connection_factory = connection_factory
        if not self.dsn:
            raise RuntimeStorageConfigError('postgres runtime state storage requires DSN')

    def _connect(self):
        if self._connection_factory is not None:
            return self._connection_factory()
        assert psycopg is not None and dict_row is not None
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def _entity_count(self, conn: Any, entity: str) -> int | None:
        try:
            with conn.cursor() as cur:
                cur.execute(f'SELECT COUNT(*) AS n FROM {entity}')
                row = cur.fetchone()
                if not row:
                    return 0
                if isinstance(row, dict):
                    return int(row.get('n') or 0)
                return int(row[0])
        except Exception:
            return None

    def diagnostics(self) -> RuntimeStateDiagnostics:
        settings = get_settings()
        runtime = runtime_storage_diagnostics(
            resolve_runtime_storage_settings(
                project_root=settings.project_root,
                storage_dir=settings.storage_dir,
                sqlite_db_path=settings.db_path,
            )
        )
        counts: dict[str, int | None] = {entity: None for entity in RUNTIME_STATE_ENTITIES}
        migration_status = 'postgres_runtime_state_connection_pending'
        try:
            with self._connect() as conn:
                counts = {entity: self._entity_count(conn, entity) for entity in RUNTIME_STATE_ENTITIES}
                migration_status = 'postgres_runtime_state_live' if all(v is not None for v in counts.values()) else 'postgres_runtime_state_partial'
        except Exception:
            migration_status = 'postgres_runtime_state_connection_failed'
        entities = tuple(
            RuntimeStateEntityStatus(
                entity=entity,
                backend='postgres',
                primary_state=True,
                legacy_sqlite_primary=False,
                migrated=True,
                count=counts.get(entity),
                index_hints=ENTITY_INDEX_HINTS.get(entity, ()),
                retention_note=ENTITY_RETENTION_NOTES.get(entity, ''),
            )
            for entity in RUNTIME_STATE_ENTITIES
        )
        return RuntimeStateDiagnostics(
            backend='postgres',
            profile=str(runtime.profile),
            adult_mode=bool(runtime.adult_mode),
            compat_mode=bool(runtime.compat_mode),
            migration_status=migration_status,
            primary_runtime_state_backend='postgres',
            support_bundle_legacy_web_db_default=False,
            restore_legacy_web_db_default=False,
            maintenance_notes={
                'vacuum_guidance': 'Use PostgreSQL autovacuum plus targeted VACUUM (ANALYZE) after heavy backfill windows.',
                'index_guidance': 'Review btree indexes on tenant/status/created_at lineage columns; reindex only when bloat evidence exists.',
                'recovery_model': 'Use pg_dump / physical backups for runtime state; legacy web.db should not be the default restore source for migrated entities.',
            },
            entities=entities,
        )


def _sqlite_counts(conn: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for entity in RUNTIME_STATE_ENTITIES:
        try:
            out[entity] = int(conn.execute(f'SELECT COUNT(*) FROM {entity}').fetchone()[0])
        except Exception:
            out[entity] = 0
    return out


def resolve_runtime_state_storage(*, conn: Any | None = None) -> SqliteCompatRuntimeStateStorage | PostgresRuntimeStateStorage:
    settings = get_settings()
    backend = str(settings.runtime_storage_backend or 'postgres')
    if backend == 'postgres':
        runtime = resolve_runtime_storage_settings(
            project_root=settings.project_root,
            storage_dir=settings.storage_dir,
            sqlite_db_path=settings.db_path,
        )
        return PostgresRuntimeStateStorage(dsn=str(runtime.postgres_dsn or ''))
    return SqliteCompatRuntimeStateStorage(db_path=settings.db_path)


def runtime_state_storage_diagnostics(*, conn: Any | None = None) -> RuntimeStateDiagnostics:
    storage = resolve_runtime_state_storage(conn=conn)
    return storage.diagnostics()


def build_runtime_state_summary_payload(*, conn: Any | None = None) -> dict[str, Any]:
    return runtime_state_storage_diagnostics(conn=conn).as_dict()


__all__ = [
    'RUNTIME_STATE_ENTITIES',
    'RuntimeStateEntityStatus',
    'RuntimeStateDiagnostics',
    'SqliteCompatRuntimeStateStorage',
    'PostgresRuntimeStateStorage',
    'resolve_runtime_state_storage',
    'runtime_state_storage_diagnostics',
    'build_runtime_state_summary_payload',
]

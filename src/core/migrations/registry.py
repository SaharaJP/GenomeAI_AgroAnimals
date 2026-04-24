from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable


SCHEMA_REGISTRY_TABLE = "schema_registry"
WEB_DB_SCHEMA_VERSION = 9
AUDIT_LOG_SCHEMA_VERSION = 2
JOBS_SCHEMA_VERSION = 2
CONNECTOR_RUNS_SCHEMA_VERSION = 2
ANIMAL_EVENTS_SCHEMA_VERSION = 1
BACKUP_FORMAT_SCHEMA_VERSION = 2
PILOT_PACK_FORMAT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class MigrationComponent:
    component: str
    current_version: int
    supported_from: int
    kind: str
    description: str


@dataclass(frozen=True)
class MigrationDiagnostic:
    component: str
    code: str
    message: str
    remediation: str
    current_version: int | None = None
    supported_from: int | None = None
    detected_version: int | None = None
    field: str | None = None
    example: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


class MigrationCompatibilityError(RuntimeError):
    def __init__(self, diagnostic: MigrationDiagnostic):
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)

    def as_dict(self) -> dict[str, Any]:
        return self.diagnostic.as_dict()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def migration_registry() -> list[MigrationComponent]:
    return [
        MigrationComponent(
            component="web.db",
            current_version=WEB_DB_SCHEMA_VERSION,
            supported_from=1,
            kind="sqlite",
            description="Web cabinet runtime DB schema and online migrations.",
        ),
        MigrationComponent(
            component="web.db.audit_log",
            current_version=AUDIT_LOG_SCHEMA_VERSION,
            supported_from=1,
            kind="sqlite-table",
            description="Append-only audit log with action_group/object_ref/schema_version/archival metadata.",
        ),
        MigrationComponent(
            component="web.db.jobs",
            current_version=JOBS_SCHEMA_VERSION,
            supported_from=1,
            kind="sqlite-table",
            description="Job runner table with public_job_id/queue/retry/run lineage fields.",
        ),
        MigrationComponent(
            component="web.db.connector_runs",
            current_version=CONNECTOR_RUNS_SCHEMA_VERSION,
            supported_from=1,
            kind="sqlite-table",
            description="Connector run journal including partial status support.",
        ),
        MigrationComponent(
            component="web.db.animal_events",
            current_version=ANIMAL_EVENTS_SCHEMA_VERSION,
            supported_from=1,
            kind="sqlite-table",
            description="Unified append-only operational animal event log with task/decision/version linkage.",
        ),
        MigrationComponent(
            component="web.db.completion_outcomes",
            current_version=1,
            supported_from=1,
            kind="sqlite-table",
            description="Append-only completion/outcome loop records linked to worklists/tasks/alerts/decisions.",
        ),
        MigrationComponent(
            component="web.db.vet_protocol_executions",
            current_version=1,
            supported_from=1,
            kind="sqlite-table",
            description="Versioned vet protocol execution log with steps, follow-ups, linked treatments/observations and workflow linkage.",
        ),
        MigrationComponent(
            component="web.db.treatment_journal",
            current_version=1,
            supported_from=1,
            kind="sqlite-table",
            description="Treatment courses / withdrawal windows / follow-up journal with audit-logged changes and source-version linkage.",
        ),
        MigrationComponent(
            component="backup_manifest",
            current_version=BACKUP_FORMAT_SCHEMA_VERSION,
            supported_from=1,
            kind="artifact-manifest",
            description="Backup/restore archive manifest format versions v1..v2.",
        ),
        MigrationComponent(
            component="pilot_pack",
            current_version=PILOT_PACK_FORMAT_SCHEMA_VERSION,
            supported_from=1,
            kind="artifact-manifest",
            description="Offline pilot pack import format based on versions.json + optional pack_manifest.json.",
        ),
    ]


def registry_snapshot() -> dict[str, Any]:
    items = [asdict(item) for item in migration_registry()]
    return {
        "schema": "genomeai.migration_registry.v1",
        "generated_at": utcnow_iso(),
        "items": items,
    }


def ensure_schema_registry_table(conn: Any) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA_REGISTRY_TABLE} (
          component TEXT PRIMARY KEY,
          version INTEGER NOT NULL,
          updated_at TEXT NOT NULL,
          details_json TEXT NOT NULL DEFAULT '{{}}'
        )
        """
    )


def load_schema_registry(conn: Any) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    try:
        result = conn.execute(
            f"SELECT component, version, updated_at, details_json FROM {SCHEMA_REGISTRY_TABLE}"
        )
    except Exception:
        return rows
    for row in result.fetchall() if hasattr(result, 'fetchall') else []:
        try:
            details = json.loads(str(row[3] or "{}"))
        except Exception:
            details = {"raw": row[3]}
        rows[str(row[0])] = {
            "component": str(row[0]),
            "version": int(row[1]),
            "updated_at": str(row[2]),
            "details": details,
        }
    return rows


def upsert_schema_version(
    conn: Any,
    *,
    component: str,
    version: int,
    details: dict[str, Any] | None = None,
) -> None:
    ensure_schema_registry_table(conn)
    conn.execute(
        f"""
        INSERT INTO {SCHEMA_REGISTRY_TABLE}(component, version, updated_at, details_json)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(component) DO UPDATE SET
          version=excluded.version,
          updated_at=excluded.updated_at,
          details_json=excluded.details_json
        """,
        (component, int(version), utcnow_iso(), json.dumps(details or {}, ensure_ascii=False, sort_keys=True)),
    )


def sync_runtime_schema_registry(
    conn: Any,
    *,
    notes: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    ensure_schema_registry_table(conn)
    registry_notes = notes or {}
    for item in migration_registry():
        if not item.component.startswith("web.db"):
            continue
        details = {
            "kind": item.kind,
            "supported_from": item.supported_from,
            "description": item.description,
        }
        details.update(registry_notes.get(item.component, {}))
        upsert_schema_version(conn, component=item.component, version=item.current_version, details=details)
    return load_schema_registry(conn)


def _component_meta(component: str) -> MigrationComponent | None:
    for item in migration_registry():
        if item.component == component:
            return item
    return None


def validate_schema_registry(conn: Any) -> None:
    existing = load_schema_registry(conn)
    for component, row in existing.items():
        meta = _component_meta(component)
        if meta is None:
            continue
        detected = int(row["version"])
        if detected > meta.current_version:
            raise MigrationCompatibilityError(
                MigrationDiagnostic(
                    component=component,
                    code="migration.future_version",
                    message=(
                        f"{component}: snapshot/schema version {detected} is newer than supported {meta.current_version}."
                    ),
                    remediation="Use the same or newer GenomeAI release, or restore from a supported snapshot/archive.",
                    current_version=meta.current_version,
                    supported_from=meta.supported_from,
                    detected_version=detected,
                    field="schema_registry.version",
                    example=f"{{\"component\": \"{component}\", \"version\": {meta.current_version}}}",
                )
            )
        if detected < meta.supported_from:
            raise MigrationCompatibilityError(
                MigrationDiagnostic(
                    component=component,
                    code="migration.too_old",
                    message=(
                        f"{component}: snapshot/schema version {detected} is older than supported minimum {meta.supported_from}."
                    ),
                    remediation="Restore through an intermediate supported release or recreate the runtime state from a supported backup.",
                    current_version=meta.current_version,
                    supported_from=meta.supported_from,
                    detected_version=detected,
                    field="schema_registry.version",
                    example=f"minimum supported version for {component}: {meta.supported_from}",
                )
            )


def supported_range(component: str) -> tuple[int, int]:
    meta = _component_meta(component)
    if meta is None:
        raise KeyError(component)
    return (meta.supported_from, meta.current_version)


def artifact_version_diagnostic(
    *,
    component: str,
    detected_version: int,
    field: str,
    example: str,
) -> MigrationDiagnostic:
    supported_from, current = supported_range(component)
    if detected_version > current:
        code = "migration.future_version"
        message = f"{component}: version {detected_version} is newer than supported {current}."
        remediation = "Use the same or newer GenomeAI release, or export the archive using a supported format."
    else:
        code = "migration.too_old"
        message = f"{component}: version {detected_version} is older than supported minimum {supported_from}."
        remediation = "Re-export the archive using a supported release or restore through an intermediate supported version."
    return MigrationDiagnostic(
        component=component,
        code=code,
        message=message,
        remediation=remediation,
        current_version=current,
        supported_from=supported_from,
        detected_version=detected_version,
        field=field,
        example=example,
    )


__all__ = [
    "AUDIT_LOG_SCHEMA_VERSION",
    "BACKUP_FORMAT_SCHEMA_VERSION",
    "CONNECTOR_RUNS_SCHEMA_VERSION",
    "JOBS_SCHEMA_VERSION",
    "MigrationCompatibilityError",
    "MigrationComponent",
    "MigrationDiagnostic",
    "PILOT_PACK_FORMAT_SCHEMA_VERSION",
    "SCHEMA_REGISTRY_TABLE",
    "WEB_DB_SCHEMA_VERSION",
    "artifact_version_diagnostic",
    "ensure_schema_registry_table",
    "load_schema_registry",
    "migration_registry",
    "registry_snapshot",
    "supported_range",
    "sync_runtime_schema_registry",
    "upsert_schema_version",
    "utcnow_iso",
    "validate_schema_registry",
]

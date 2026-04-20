from __future__ import annotations

from typing import Any, Mapping

from core.migrations.registry import (
    BACKUP_FORMAT_SCHEMA_VERSION,
    MigrationCompatibilityError,
    PILOT_PACK_FORMAT_SCHEMA_VERSION,
    artifact_version_diagnostic,
)

BACKUP_FORMAT_TO_VERSION = {
    "genomeai_backup_v1": 1,
    "genomeai_backup_v2": 2,
}
VERSION_TO_BACKUP_FORMAT = {v: k for k, v in BACKUP_FORMAT_TO_VERSION.items()}


def validate_backup_manifest_compatibility(manifest: Mapping[str, Any]) -> dict[str, Any]:
    backup_format = str(manifest.get("format") or VERSION_TO_BACKUP_FORMAT[1])
    version = BACKUP_FORMAT_TO_VERSION.get(backup_format)
    if version is None:
        raise MigrationCompatibilityError(
            artifact_version_diagnostic(
                component="backup_manifest",
                detected_version=BACKUP_FORMAT_SCHEMA_VERSION + 1,
                field="manifest.format",
                example='{"format": "genomeai_backup_v2"}',
            )
        )
    if version > BACKUP_FORMAT_SCHEMA_VERSION:
        raise MigrationCompatibilityError(
            artifact_version_diagnostic(
                component="backup_manifest",
                detected_version=version,
                field="manifest.format",
                example='{"format": "genomeai_backup_v2"}',
            )
        )
    return {
        "format": backup_format,
        "format_version": version,
        "manifest": dict(manifest),
    }


def detect_pilot_pack_version(versions_payload: Mapping[str, Any]) -> int:
    raw = versions_payload.get("pack_schema_version")
    if raw is None:
        return 1
    try:
        return int(raw)
    except Exception as exc:  # pragma: no cover - extremely defensive
        raise MigrationCompatibilityError(
            artifact_version_diagnostic(
                component="pilot_pack",
                detected_version=PILOT_PACK_FORMAT_SCHEMA_VERSION + 1,
                field="versions.json.pack_schema_version",
                example='{"pack_schema_version": 1}',
            )
        ) from exc


def validate_pilot_pack_versions(versions_payload: Mapping[str, Any]) -> dict[str, Any]:
    pack_version = detect_pilot_pack_version(versions_payload)
    if pack_version > PILOT_PACK_FORMAT_SCHEMA_VERSION or pack_version < 1:
        raise MigrationCompatibilityError(
            artifact_version_diagnostic(
                component="pilot_pack",
                detected_version=pack_version,
                field="versions.json.pack_schema_version",
                example='{"pack_schema_version": 1, "data_version": "dv_20260320"}',
            )
        )

    aliases = {
        "data_version": ["data_version", "dv"],
        "qc_run": ["qc_run"],
        "model_version": ["model_version", "mv"],
        "scoring_run": ["scoring_run", "sr"],
        "report_version": ["report_version", "rv"],
        "pack_id": ["pack_id"],
    }
    normalized: dict[str, Any] = {"pack_schema_version": pack_version}
    for canonical, candidates in aliases.items():
        value = None
        for key in candidates:
            raw = versions_payload.get(key)
            if raw not in (None, ""):
                value = raw
                break
        normalized[canonical] = value
    return normalized


__all__ = [
    "BACKUP_FORMAT_TO_VERSION",
    "VERSION_TO_BACKUP_FORMAT",
    "detect_pilot_pack_version",
    "validate_backup_manifest_compatibility",
    "validate_pilot_pack_versions",
]

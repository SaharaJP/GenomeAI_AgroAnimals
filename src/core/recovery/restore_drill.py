from __future__ import annotations

import fnmatch
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

from genomeai.backup_restore import (
    _normalize_db_path,
    _write_best_effort_audit,
    make_backup,
    restore_backup,
)


_DEFAULT_RESTORE_DRILL_POLICY: dict[str, Any] = {
    "version": 1,
    "report_dir": "artifacts/restore_drills",
    "smoke_check": True,
    "keep_restore_snapshot_on_success": False,
    "keep_restore_snapshot_on_failure": True,
    "selected_artifact_globs": [
        "**/manifest.json",
        "**/report*.json",
        "**/report*.md",
        "**/fact_pack*.json",
        "**/fact_pack*.md",
        "**/decision*.json",
        "**/tasks*.json",
    ],
    "db_tables": [
        "audit_log",
        "jobs",
        "decision_log_v2",
        "tasks_v1",
    ],
    "audit_ignore_actions": [
        "backup.restore",
        "backup.drill",
        "backup.drill.start",
        "backup.drill.complete",
        "backup.drill.failed",
    ],
    "max_examples": 10,
}


class RestoreDrillError(ValueError):
    """Human-readable restore drill error."""


def _utc_ts_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _read_yaml_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise RestoreDrillError(f"{path}: ожидался YAML-объект верхнего уровня")
    return raw


def load_restore_drill_policy(*, project_root: str | Path = ".", config_path: str | Path | None = None) -> dict[str, Any]:
    project_root_path = Path(project_root).resolve()
    path = Path(config_path).resolve() if config_path is not None else (project_root_path / "configs" / "ops" / "backup_restore_drill_v1.yaml").resolve()
    raw = _read_yaml_dict(path)
    cfg = _deep_merge(_json_clone(_DEFAULT_RESTORE_DRILL_POLICY), raw)
    try:
        cfg["version"] = int(cfg.get("version", 1))
    except Exception as exc:
        raise RestoreDrillError(f"{path}: version должен быть целым числом") from exc
    for key in ["report_dir"]:
        value = str(cfg.get(key) or "").strip().strip("/")
        if not value:
            raise RestoreDrillError(f"{path}: {key} должен быть непустой строкой")
        cfg[key] = value
    for key in ["smoke_check", "keep_restore_snapshot_on_success", "keep_restore_snapshot_on_failure"]:
        cfg[key] = bool(cfg.get(key, _DEFAULT_RESTORE_DRILL_POLICY[key]))
    selected_globs = cfg.get("selected_artifact_globs") or []
    if not isinstance(selected_globs, list) or not selected_globs:
        raise RestoreDrillError(f"{path}: selected_artifact_globs должен быть непустым списком")
    cfg["selected_artifact_globs"] = [str(item).strip() for item in selected_globs if str(item).strip()]
    db_tables = cfg.get("db_tables") or []
    if not isinstance(db_tables, list):
        raise RestoreDrillError(f"{path}: db_tables должен быть списком")
    cfg["db_tables"] = [str(item).strip() for item in db_tables if str(item).strip()]
    audit_ignore = cfg.get("audit_ignore_actions") or []
    if not isinstance(audit_ignore, list):
        raise RestoreDrillError(f"{path}: audit_ignore_actions должен быть списком")
    cfg["audit_ignore_actions"] = [str(item).strip() for item in audit_ignore if str(item).strip()]
    try:
        cfg["max_examples"] = int(cfg.get("max_examples", 10))
    except Exception as exc:
        raise RestoreDrillError(f"{path}: max_examples должен быть целым числом") from exc
    if cfg["max_examples"] < 1:
        raise RestoreDrillError(f"{path}: max_examples должен быть >= 1")
    cfg["path"] = str(path)
    cfg["project_root"] = str(project_root_path)
    return cfg


def _matches_any(rel_path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(rel_path, str(pattern)) for pattern in patterns)


def _collect_selected_files(root: Path, patterns: Iterable[str]) -> dict[str, dict[str, Any]]:
    if not root.exists():
        return {}
    collected: dict[str, dict[str, Any]] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        if not _matches_any(rel, patterns):
            continue
        collected[rel] = {
            "rel_path": rel,
            "size": int(path.stat().st_size),
            "sha256": _sha256_file(path),
        }
    return collected


def compare_selected_artifacts(*, source_root: Path, restored_root: Path, patterns: Iterable[str], max_examples: int = 10) -> dict[str, Any]:
    source_files = _collect_selected_files(source_root, patterns)
    restored_files = _collect_selected_files(restored_root, patterns)
    all_paths = sorted(set(source_files) | set(restored_files))
    mismatches: list[dict[str, Any]] = []
    matched = 0
    for rel in all_paths:
        source_meta = source_files.get(rel)
        restored_meta = restored_files.get(rel)
        if source_meta is None:
            mismatches.append({"path": rel, "reason": "unexpected_in_restore"})
            continue
        if restored_meta is None:
            mismatches.append({"path": rel, "reason": "missing_after_restore"})
            continue
        if source_meta["sha256"] != restored_meta["sha256"]:
            mismatches.append(
                {
                    "path": rel,
                    "reason": "checksum_mismatch",
                    "source_sha256": source_meta["sha256"],
                    "restored_sha256": restored_meta["sha256"],
                }
            )
            continue
        matched += 1
    return {
        "ok": not mismatches,
        "selected_globs": list(patterns),
        "source_file_count": len(source_files),
        "restored_file_count": len(restored_files),
        "matched_files": matched,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:max_examples],
        "source_files": source_files,
        "restored_files": restored_files,
    }


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(row[1]) for row in rows]


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone()
    return row is not None


def _digest_rows(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_table_rows(conn: sqlite3.Connection, table_name: str, *, audit_ignore_actions: Iterable[str]) -> tuple[list[dict[str, Any]], str]:
    columns = _table_columns(conn, table_name)
    if not columns:
        return [], ""
    order_col = "id" if "id" in columns else columns[0]
    query = f"SELECT * FROM {table_name}"
    params: list[Any] = []
    if table_name == "audit_log" and audit_ignore_actions:
        placeholders = ",".join("?" for _ in audit_ignore_actions)
        query += f" WHERE action NOT IN ({placeholders})"
        params.extend(list(audit_ignore_actions))
    query += f" ORDER BY {order_col}"
    cursor = conn.execute(query, params)
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return rows, order_col


def compare_sqlite_tables(*, source_db: Path, restored_db: Path, tables: Iterable[str], audit_ignore_actions: Iterable[str], max_examples: int = 10) -> dict[str, Any]:
    if not source_db.exists():
        raise RestoreDrillError(f"source db not found: {source_db}")
    if not restored_db.exists():
        raise RestoreDrillError(f"restored db not found: {restored_db}")
    source_conn = sqlite3.connect(str(source_db))
    restored_conn = sqlite3.connect(str(restored_db))
    try:
        details: dict[str, Any] = {}
        mismatch_count = 0
        for table_name in tables:
            source_exists = _table_exists(source_conn, table_name)
            restored_exists = _table_exists(restored_conn, table_name)
            if not source_exists and not restored_exists:
                details[table_name] = {"status": "absent_in_both", "ok": True}
                continue
            if source_exists != restored_exists:
                mismatch_count += 1
                details[table_name] = {
                    "status": "table_presence_mismatch",
                    "ok": False,
                    "source_exists": source_exists,
                    "restored_exists": restored_exists,
                }
                continue
            source_rows, source_order = _load_table_rows(source_conn, table_name, audit_ignore_actions=audit_ignore_actions)
            restored_rows, restored_order = _load_table_rows(restored_conn, table_name, audit_ignore_actions=audit_ignore_actions)
            source_digest = _digest_rows(source_rows)
            restored_digest = _digest_rows(restored_rows)
            table_ok = source_digest == restored_digest and len(source_rows) == len(restored_rows)
            if not table_ok:
                mismatch_count += 1
            details[table_name] = {
                "status": "ok" if table_ok else "content_mismatch",
                "ok": table_ok,
                "source_row_count": len(source_rows),
                "restored_row_count": len(restored_rows),
                "source_digest": source_digest,
                "restored_digest": restored_digest,
                "order_column": source_order or restored_order,
                "examples": {
                    "source_head": source_rows[:max_examples],
                    "restored_head": restored_rows[:max_examples],
                } if not table_ok else {},
            }
        return {
            "ok": mismatch_count == 0,
            "table_count": len(list(tables)),
            "mismatch_count": mismatch_count,
            "tables": details,
            "audit_ignore_actions": list(audit_ignore_actions),
        }
    finally:
        source_conn.close()
        restored_conn.close()


def _render_restore_drill_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    restore = report.get("restore") or {}
    artifact_compare = report.get("artifact_compare") or {}
    db_compare = report.get("db_compare") or {}
    lines = [
        "# Backup/restore drill report",
        "",
        f"- drill_id: `{report.get('drill_id')}`",
        f"- ok: `{bool(summary.get('ok'))}`",
        f"- backup_zip: `{report.get('backup_zip')}`",
        f"- report_generated_at: `{report.get('generated_at')}`",
        f"- source_artifacts_root: `{report.get('source', {}).get('artifacts_root')}`",
        f"- source_web_storage: `{report.get('source', {}).get('web_storage')}`",
        f"- restore_verified_files: `{restore.get('verified_files')}` / `{restore.get('total_files')}`",
        f"- restore_smoke_ok: `{bool((restore.get('smoke') or {}).get('ok'))}`",
        f"- selected_artifact_mismatches: `{artifact_compare.get('mismatch_count')}`",
        f"- db_mismatches: `{db_compare.get('mismatch_count')}`",
        "",
        "## Diagnostics",
        "",
    ]
    if summary.get("reason"):
        lines.append(f"- reason: {summary.get('reason')}")
    if artifact_compare.get("mismatches"):
        lines.append("- artifact mismatches:")
        for item in artifact_compare.get("mismatches") or []:
            lines.append(f"  - {item.get('path')}: {item.get('reason')}")
    if db_compare.get("tables"):
        lines.append("- db tables:")
        for table_name, detail in sorted((db_compare.get("tables") or {}).items()):
            lines.append(f"  - {table_name}: {detail.get('status')}")
    lines.extend([
        "",
        "## Restore paths",
        "",
        f"- restored_artifacts_root: `{report.get('restore_paths', {}).get('artifacts_root')}`",
        f"- restored_web_storage: `{report.get('restore_paths', {}).get('web_storage')}`",
        f"- restored_db_path: `{report.get('restore_paths', {}).get('db_path')}`",
        f"- restore_snapshot_kept: `{bool(report.get('restore_paths', {}).get('kept'))}`",
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


def run_restore_drill(*, project_root: str | Path = ".", artifacts_root: str | Path, web_storage: str | Path, db_path: str | Path | None = None, report_root: str | Path | None = None, config_path: str | Path | None = None) -> dict[str, Any]:
    project_root_path = Path(project_root).resolve()
    artifacts_root_path = Path(artifacts_root).resolve()
    web_storage_path = Path(web_storage).resolve()
    db_path_obj = _normalize_db_path(web_storage_path, Path(db_path).resolve() if db_path is not None else None)
    policy = load_restore_drill_policy(project_root=project_root_path, config_path=config_path)
    drill_id = f"restore_drill_{_utc_ts_compact()}"
    report_base = Path(report_root).resolve() if report_root is not None else (project_root_path / str(policy["report_dir"]))
    drill_root = (report_base / drill_id).resolve()
    backup_dir = drill_root / "backup"
    restored_root = drill_root / "restored"
    restored_artifacts = restored_root / "artifacts"
    restored_web_storage = restored_root / "web_storage"
    restored_db_path = restored_web_storage / db_path_obj.name
    backup_dir.mkdir(parents=True, exist_ok=True)
    report_json_path = drill_root / "restore_drill_report.json"
    report_md_path = drill_root / "restore_drill_report.md"
    backup_zip_path = backup_dir / f"{drill_id}.zip"

    try:
        backup_result = make_backup(
            artifacts_root=artifacts_root_path,
            web_storage=web_storage_path,
            db_path=db_path_obj,
            out_zip=backup_zip_path,
            project_root=project_root_path,
        )
        restore_result = restore_backup(
            backup_zip=backup_zip_path,
            artifacts_root=restored_artifacts,
            web_storage=restored_web_storage,
            db_path=restored_db_path,
            force=True,
            smoke_check=bool(policy.get("smoke_check", True)),
        )
    except Exception as exc:
        message = exc if isinstance(exc, RestoreDrillError) else RestoreDrillError(f"restore drill failed: {type(exc).__name__}: {exc}")
        _write_best_effort_audit(
            db_path=db_path_obj,
            action="backup.drill",
            object_id=drill_id,
            status="ERROR",
            after={
                "backup_zip": str(backup_zip_path),
                "config_path": policy.get("path"),
            },
            error=str(message),
        )
        raise message

    artifact_compare: dict[str, Any] = {
        "ok": False,
        "mismatch_count": 0,
        "mismatches": [],
        "selected_globs": list(policy.get("selected_artifact_globs") or []),
    }
    db_compare: dict[str, Any] = {
        "ok": False,
        "mismatch_count": 0,
        "tables": {},
    }
    reason = None
    if restore_result.get("ok"):
        artifact_compare = compare_selected_artifacts(
            source_root=artifacts_root_path,
            restored_root=restored_artifacts,
            patterns=policy.get("selected_artifact_globs") or [],
            max_examples=int(policy.get("max_examples", 10)),
        )
        db_compare = compare_sqlite_tables(
            source_db=db_path_obj,
            restored_db=restored_db_path,
            tables=policy.get("db_tables") or [],
            audit_ignore_actions=policy.get("audit_ignore_actions") or [],
            max_examples=int(policy.get("max_examples", 10)),
        )
    else:
        reason = str(restore_result.get("reason") or "restore_failed")

    ok = bool(restore_result.get("ok")) and bool(artifact_compare.get("ok")) and bool(db_compare.get("ok"))
    if reason is None and not artifact_compare.get("ok"):
        reason = f"artifact_compare_mismatch_count={artifact_compare.get('mismatch_count')}"
    if reason is None and not db_compare.get("ok"):
        reason = f"db_compare_mismatch_count={db_compare.get('mismatch_count')}"

    keep_snapshot = bool(policy.get("keep_restore_snapshot_on_failure", True)) if not ok else bool(policy.get("keep_restore_snapshot_on_success", False))
    report = {
        "schema": "genomeai.restore_drill.report.v1",
        "version": 1,
        "drill_id": drill_id,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "policy": {
            "path": policy.get("path"),
            "version": policy.get("version"),
            "smoke_check": policy.get("smoke_check"),
            "selected_artifact_globs": list(policy.get("selected_artifact_globs") or []),
            "db_tables": list(policy.get("db_tables") or []),
            "audit_ignore_actions": list(policy.get("audit_ignore_actions") or []),
        },
        "source": {
            "project_root": str(project_root_path),
            "artifacts_root": str(artifacts_root_path),
            "web_storage": str(web_storage_path),
            "db_path": str(db_path_obj),
        },
        "backup_zip": str(backup_zip_path),
        "backup": {
            "backup_id": backup_result.backup_id,
            "backup_zip": backup_result.backup_zip,
            "file_count": backup_result.file_count,
        },
        "restore": restore_result,
        "report_paths": {"json": str(report_json_path), "md": str(report_md_path)},
        "artifact_compare": artifact_compare,
        "db_compare": db_compare,
        "restore_paths": {
            "artifacts_root": str(restored_artifacts),
            "web_storage": str(restored_web_storage),
            "db_path": str(restored_db_path),
            "kept": keep_snapshot,
        },
        "summary": {
            "ok": ok,
            "reason": reason,
            "restore_ok": bool(restore_result.get("ok")),
            "restore_verified_files": int(restore_result.get("verified_files") or 0),
            "restore_total_files": int(restore_result.get("total_files") or 0),
            "artifact_mismatches": int(artifact_compare.get("mismatch_count") or 0),
            "db_mismatches": int(db_compare.get("mismatch_count") or 0),
        },
    }
    drill_root.mkdir(parents=True, exist_ok=True)
    report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_md_path.write_text(_render_restore_drill_markdown(report), encoding="utf-8")

    _write_best_effort_audit(
        db_path=db_path_obj,
        action="backup.drill",
        object_id=drill_id,
        status="OK" if ok else "ERROR",
        after={
            "backup_zip": str(backup_zip_path),
            "report_json": str(report_json_path),
            "report_md": str(report_md_path),
            "restore_verified_files": int(restore_result.get("verified_files") or 0),
            "restore_total_files": int(restore_result.get("total_files") or 0),
            "artifact_mismatches": int(artifact_compare.get("mismatch_count") or 0),
            "db_mismatches": int(db_compare.get("mismatch_count") or 0),
            "restore_smoke_ok": bool((restore_result.get("smoke") or {}).get("ok")) if isinstance(restore_result.get("smoke"), dict) else None,
        },
        error=reason,
    )

    if not keep_snapshot and restored_root.exists():
        shutil.rmtree(restored_root, ignore_errors=True)
        report["restore_paths"]["kept"] = False
        report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report_md_path.write_text(_render_restore_drill_markdown(report), encoding="utf-8")

    return report


def render_restore_drill_cli_lines(result: dict[str, Any]) -> list[str]:
    summary = result.get("summary") or {}
    restore = result.get("restore") or {}
    lines = ["RESTORE_DRILL_OK" if summary.get("ok") else "RESTORE_DRILL_FAILED"]
    lines.append(f"drill_id={result.get('drill_id')}")
    lines.append(f"backup_zip={result.get('backup_zip')}")
    lines.append(f"report_json={result.get('report_paths', {}).get('json') or ''}")
    lines.append(f"report_md={result.get('report_paths', {}).get('md') or ''}")
    lines.append(f"restore_verified_files={restore.get('verified_files')}")
    lines.append(f"restore_total_files={restore.get('total_files')}")
    lines.append(f"artifact_mismatches={summary.get('artifact_mismatches')}")
    lines.append(f"db_mismatches={summary.get('db_mismatches')}")
    if summary.get("reason"):
        lines.append(f"reason={summary.get('reason')}")
    return lines


__all__ = [
    "RestoreDrillError",
    "compare_selected_artifacts",
    "compare_sqlite_tables",
    "load_restore_drill_policy",
    "render_restore_drill_cli_lines",
    "run_restore_drill",
]

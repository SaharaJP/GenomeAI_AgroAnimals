from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

from core.artifacts.lifecycle import build_support_bundle
from core.config import validate_startup_config_bundle
from core.observability.competitive_acceptance import load_competitive_acceptance_policy
from core.observability.operational_gates import load_operational_rollout_gates_policy
from core.recovery import load_restore_drill_policy, run_restore_drill
from core.release import build_release_package, load_release_metadata, run_release_package_smoke
from genomeai.backup_restore import _normalize_db_path, _write_best_effort_audit, make_backup


_DEFAULT_CUSTOMER_UPGRADE_POLICY: dict[str, Any] = {
    "version": 1,
    "report_dir": "artifacts/customer_upgrade_v1",
    "release_notes_path": "data/release/release_notes_v1.json",
    "build_support_bundle": True,
    "build_backup_preview": True,
    "run_restore_drill": True,
    "build_release_package": True,
    "pre_upgrade_checks": [
        {"id": "runtime_paths", "label": "Runtime roots available", "required": True},
        {"id": "release_metadata", "label": "Release metadata available", "required": True},
        {"id": "startup_bundle", "label": "Startup config bundle valid", "required": True},
        {"id": "release_notes", "label": "Release notes linked", "required": True},
        {"id": "support_bundle", "label": "Support bundle built", "required": True},
        {"id": "backup_preview", "label": "Pre-upgrade backup preview built", "required": True},
    ],
    "post_upgrade_checks": [
        {"id": "restore_drill", "label": "Backup / restore drill ok", "required": True},
        {"id": "release_package_smoke", "label": "Release package smoke ok", "required": True},
        {"id": "release_diagnostics", "label": "Release diagnostics available", "required": True},
        {"id": "restore_diagnostics", "label": "Restore diagnostics linked", "required": True},
        {"id": "operational_rollout_policy", "label": "Operational rollout diagnostics policy linked", "required": False},
        {"id": "competitive_acceptance_policy", "label": "Competitive acceptance policy linked", "required": False},
    ],
    "rollback_criteria": [
        {
            "criterion_id": "missing_pre_upgrade_backup",
            "severity": "critical",
            "description": "Rollback / stop if pre-upgrade backup preview could not be created.",
        },
        {
            "criterion_id": "restore_drill_failed",
            "severity": "critical",
            "description": "Rollback / stop if restore drill fails or cannot verify restored artifacts and DB tables.",
        },
        {
            "criterion_id": "release_package_smoke_failed",
            "severity": "critical",
            "description": "Rollback / stop if packaged release cannot pass manifest + CLI/API smoke.",
        },
        {
            "criterion_id": "startup_bundle_invalid",
            "severity": "critical",
            "description": "Rollback / stop if startup bundle is not readable and versioned for the target release.",
        },
        {
            "criterion_id": "release_notes_missing",
            "severity": "warn",
            "description": "Do not upgrade without change summary, known issues and diagnostics linkage.",
        },
    ],
    "manual_checklist": [
        "Confirm target customer window and maintenance owner.",
        "Communicate rollback criteria and support contact before upgrade.",
        "Run the generated repeatable checks before touching the live environment.",
    ],
}


class CustomerUpgradeDisciplineError(ValueError):
    """Human-readable upgrade discipline error."""


class _PathEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:  # pragma: no cover - defensive
        if isinstance(obj, Path):
            return str(obj)
        return super().default(obj)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_clone(value: Any) -> Any:
    return json.loads(json.dumps(value, cls=_PathEncoder))


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
        raise CustomerUpgradeDisciplineError(f"{path}: ожидался YAML-объект верхнего уровня")
    return raw


def load_customer_upgrade_policy(*, project_root: str | Path = ".", config_path: str | Path | None = None) -> dict[str, Any]:
    project_root_path = Path(project_root).resolve()
    path = Path(config_path).resolve() if config_path is not None else (project_root_path / "configs" / "ops" / "customer_upgrade_discipline_v1.yaml").resolve()
    cfg = _deep_merge(_json_clone(_DEFAULT_CUSTOMER_UPGRADE_POLICY), _read_yaml_dict(path))
    try:
        cfg["version"] = int(cfg.get("version", 1))
    except Exception as exc:  # pragma: no cover - defensive
        raise CustomerUpgradeDisciplineError(f"{path}: version должен быть целым числом") from exc
    report_dir = str(cfg.get("report_dir") or "").strip().strip("/")
    if not report_dir:
        raise CustomerUpgradeDisciplineError(f"{path}: report_dir должен быть непустой строкой")
    cfg["report_dir"] = report_dir
    release_notes_path = str(cfg.get("release_notes_path") or "").strip().strip("/")
    if not release_notes_path:
        raise CustomerUpgradeDisciplineError(f"{path}: release_notes_path должен быть непустой строкой")
    cfg["release_notes_path"] = release_notes_path
    for key in ["build_support_bundle", "build_backup_preview", "run_restore_drill", "build_release_package"]:
        cfg[key] = bool(cfg.get(key, _DEFAULT_CUSTOMER_UPGRADE_POLICY[key]))
    for list_key in ["pre_upgrade_checks", "post_upgrade_checks", "rollback_criteria", "manual_checklist"]:
        value = cfg.get(list_key) or []
        if not isinstance(value, list):
            raise CustomerUpgradeDisciplineError(f"{path}: {list_key} должен быть списком")
        cfg[list_key] = value
    cfg["path"] = str(path)
    cfg["project_root"] = str(project_root_path)
    return cfg


def load_release_notes(*, project_root: str | Path = ".", policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy_data = policy or load_customer_upgrade_policy(project_root=project_root)
    project_root_path = Path(project_root).resolve()
    path = (project_root_path / str(policy_data["release_notes_path"])).resolve()
    if not path.exists():
        return {
            "schema": "genomeai.release_notes.v1",
            "path": str(path),
            "ok": False,
            "reason": "release_notes_not_found",
            "notes": [],
        }
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CustomerUpgradeDisciplineError(f"{path}: release notes должны быть JSON-объектом")
    payload = dict(raw)
    payload["path"] = str(path)
    payload["ok"] = True
    return payload


def _find_latest_report(root: Path, filename: str) -> Path | None:
    if not root.exists():
        return None
    matches = sorted((p for p in root.rglob(filename) if p.is_file()), key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def _read_json_if_exists(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {"raw": raw}
    except Exception:
        return None


def _check_row(*, check_id: str, label: str, required: bool, ok: bool | None, detail: str, source_path: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    status = "pass" if ok else ("fail" if required else "warn") if ok is False else "info"
    return {
        "check_id": check_id,
        "label": label,
        "required": bool(required),
        "ok": ok,
        "status": status,
        "detail": detail,
        "source_path": source_path,
        "payload": payload or {},
    }


def _evaluate_required_checks(rows: Iterable[dict[str, Any]]) -> tuple[bool, int]:
    failures = 0
    for row in rows:
        if bool(row.get("required")) and row.get("ok") is not True:
            failures += 1
    return failures == 0, failures


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Customer upgrade and release discipline",
        "",
        str(report.get("summary", {}).get("statement") or ""),
        "",
        "## Summary",
        "",
        f"- pre_upgrade_ok: {report.get('summary', {}).get('pre_upgrade_ok')}",
        f"- backup_ready: {report.get('summary', {}).get('backup_ready')}",
        f"- rollback_ready: {report.get('summary', {}).get('rollback_ready')}",
        f"- post_upgrade_ok: {report.get('summary', {}).get('post_upgrade_ok')}",
        f"- upgrade_ready: {report.get('summary', {}).get('upgrade_ready')}",
        f"- rollback_recommended: {report.get('summary', {}).get('rollback_recommended')}",
        "",
        "## Pre-upgrade checks",
        "",
    ]
    for row in report.get("pre_upgrade_checks") or []:
        lines.append(f"- {row.get('check_id')}: {row.get('status')} — {row.get('detail')}")
    lines.extend(["", "## Post-upgrade verification", ""])
    for row in report.get("post_upgrade_checks") or []:
        lines.append(f"- {row.get('check_id')}: {row.get('status')} — {row.get('detail')}")
    lines.extend(["", "## Rollback criteria", ""])
    for row in report.get("rollback", {}).get("criteria") or []:
        lines.append(f"- {row.get('criterion_id')} [{row.get('severity')}]: {row.get('description')}")
    triggered = report.get("rollback", {}).get("triggered") or []
    if triggered:
        lines.extend(["", "## Triggered rollback criteria", ""])
        for row in triggered:
            lines.append(f"- {row.get('criterion_id')}: {row.get('reason')}")
    lines.extend(["", "## Release linkage", ""])
    release = report.get("release") or {}
    metadata = release.get("metadata") or {}
    lines.append(f"- release: {metadata.get('display')}")
    lines.append(f"- release notes path: {((release.get('notes') or {}).get('path'))}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_customer_upgrade_report(
    *,
    project_root: str | Path = ".",
    artifacts_root: str | Path,
    web_storage: str | Path,
    db_path: str | Path | None = None,
    report_root: str | Path | None = None,
    config_path: str | Path | None = None,
    build_support_bundle_preview: bool | None = None,
    build_backup_preview: bool | None = None,
    run_restore_drill_check: bool | None = None,
    build_release_package_preview: bool | None = None,
) -> dict[str, Any]:
    project_root_path = Path(project_root).resolve()
    artifacts_root_path = Path(artifacts_root).resolve()
    web_storage_path = Path(web_storage).resolve()
    db_path_obj = _normalize_db_path(web_storage_path, Path(db_path).resolve() if db_path is not None else None)
    policy = load_customer_upgrade_policy(project_root=project_root_path, config_path=config_path)

    support_bundle_enabled = policy["build_support_bundle"] if build_support_bundle_preview is None else bool(build_support_bundle_preview)
    backup_enabled = policy["build_backup_preview"] if build_backup_preview is None else bool(build_backup_preview)
    restore_drill_enabled = policy["run_restore_drill"] if run_restore_drill_check is None else bool(run_restore_drill_check)
    release_package_enabled = policy["build_release_package"] if build_release_package_preview is None else bool(build_release_package_preview)

    run_id = f"customer_upgrade_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    root = Path(report_root).resolve() if report_root is not None else (project_root_path / policy["report_dir"] / run_id).resolve()
    root.mkdir(parents=True, exist_ok=True)
    report_json_path = root / "customer_upgrade_report.json"
    report_md_path = root / "customer_upgrade_report.md"

    _write_best_effort_audit(
        db_path=db_path_obj,
        action="upgrade.discipline.start",
        object_id=run_id,
        after={"report_root": str(root), "policy_path": policy.get("path")},
    )
    try:
        release_metadata = load_release_metadata(project_root=project_root_path)
        release_notes = load_release_notes(project_root=project_root_path, policy=policy)
        startup = validate_startup_config_bundle(project_root_path)

        support_bundle_result: dict[str, Any] | None = None
        if support_bundle_enabled:
            support_bundle_path = root / "support_bundle.zip"
            support_bundle_result = build_support_bundle(
                output_zip=support_bundle_path,
                project_root=project_root_path,
                artifacts_root=artifacts_root_path,
                web_storage=web_storage_path,
                db_path=db_path_obj,
            )
            support_bundle_result["bundle_zip"] = str(support_bundle_path)

        backup_result: dict[str, Any] | None = None
        if backup_enabled:
            backup_path = root / "pre_upgrade_backup.zip"
            backup_preview = make_backup(
                artifacts_root=artifacts_root_path,
                web_storage=web_storage_path,
                db_path=db_path_obj,
                out_zip=backup_path,
                project_root=project_root_path,
            )
            backup_result = {
                "ok": True,
                "backup_zip": str(backup_preview.backup_zip),
                "verified_files": int(backup_preview.file_count),
                "data_versions": sorted([p.name for p in artifacts_root_path.iterdir() if p.is_dir() and p.name != 'backups']) if artifacts_root_path.exists() else [],
                "backup_id": str(backup_preview.backup_id),
            }

        restore_result: dict[str, Any] | None = None
        if restore_drill_enabled:
            restore_root = root / "restore_drill"
            restore_result = run_restore_drill(
                project_root=project_root_path,
                artifacts_root=artifacts_root_path,
                web_storage=web_storage_path,
                db_path=db_path_obj,
                report_root=restore_root,
            )

        release_package_result: dict[str, Any] | None = None
        release_package_smoke: dict[str, Any] | None = None
        if release_package_enabled:
            release_package_path = root / "release_candidate.zip"
            release_package_result = build_release_package(project_root=project_root_path, out_path=release_package_path)
            release_package_smoke = run_release_package_smoke(archive_path=release_package_path)

        latest_restore = _find_latest_report(artifacts_root_path, "restore_drill_report.json")
        latest_rollout = _find_latest_report(artifacts_root_path, "operational_rollout_gates_report.json")
        latest_competitive = _find_latest_report(artifacts_root_path, "competitive_acceptance_report.json")

        pre_rows: list[dict[str, Any]] = []
        for item in policy["pre_upgrade_checks"]:
            cid = str(item.get("id") or "")
            label = str(item.get("label") or cid)
            required = bool(item.get("required", True))
            if cid == "runtime_paths":
                ok = artifacts_root_path.exists() and web_storage_path.exists() and db_path_obj.exists()
                pre_rows.append(_check_row(check_id=cid, label=label, required=required, ok=ok, detail=f"artifacts={artifacts_root_path.exists()} web_storage={web_storage_path.exists()} db={db_path_obj.exists()}"))
            elif cid == "release_metadata":
                ok = bool(release_metadata.get("version"))
                pre_rows.append(_check_row(check_id=cid, label=label, required=required, ok=ok, detail=str(release_metadata.get("display") or "release metadata not available"), payload=release_metadata))
            elif cid == "startup_bundle":
                ok = bool(startup.get("permission_matrix_version"))
                pre_rows.append(_check_row(check_id=cid, label=label, required=required, ok=ok, detail=f"permission_matrix={startup.get('permission_matrix_version')} audit_retention={startup.get('audit_retention_version')}" , payload=startup))
            elif cid == "release_notes":
                ok = bool(release_notes.get("ok"))
                pre_rows.append(_check_row(check_id=cid, label=label, required=required, ok=ok, detail=str((release_notes.get("summary") or release_notes.get("reason") or "release notes linked")), source_path=str(release_notes.get("path") or ""), payload=release_notes))
            elif cid == "support_bundle":
                ok = bool((support_bundle_result or {}).get("ok")) if support_bundle_enabled else None
                detail = str((support_bundle_result or {}).get("bundle_zip") or ("disabled" if not support_bundle_enabled else "support bundle failed"))
                pre_rows.append(_check_row(check_id=cid, label=label, required=required, ok=ok, detail=detail, source_path=str((support_bundle_result or {}).get("bundle_zip") or ""), payload=support_bundle_result or {}))
            elif cid == "backup_preview":
                ok = bool((backup_result or {}).get("ok")) if backup_enabled else None
                detail = str((backup_result or {}).get("backup_zip") or ("disabled" if not backup_enabled else "backup preview failed"))
                pre_rows.append(_check_row(check_id=cid, label=label, required=required, ok=ok, detail=detail, source_path=str((backup_result or {}).get("backup_zip") or ""), payload=backup_result or {}))

        post_rows: list[dict[str, Any]] = []
        restore_report_path = None
        restore_summary_ok = None
        if isinstance(restore_result, dict):
            restore_report_path = str(((restore_result.get("report_paths") or {}).get("json") or restore_result.get("report_json_path") or ""))
            restore_summary_ok = (restore_result.get("summary") or {}).get("ok")
        for item in policy["post_upgrade_checks"]:
            cid = str(item.get("id") or "")
            label = str(item.get("label") or cid)
            required = bool(item.get("required", True))
            if cid == "restore_drill":
                ok = bool(restore_summary_ok) if restore_drill_enabled and restore_summary_ok is not None else None
                detail = str((restore_result or {}).get("report_json_path") or ("disabled" if not restore_drill_enabled else "restore drill failed"))
                post_rows.append(_check_row(check_id=cid, label=label, required=required, ok=ok, detail=detail, source_path=restore_report_path, payload=restore_result or {}))
            elif cid == "release_package_smoke":
                ok = bool((release_package_smoke or {}).get("ok")) if release_package_enabled else None
                detail = str((release_package_result or {}).get("archive_path") or ("disabled" if not release_package_enabled else "release package smoke failed"))
                post_rows.append(_check_row(check_id=cid, label=label, required=required, ok=ok, detail=detail, source_path=str((release_package_result or {}).get("archive_path") or ""), payload={"build": release_package_result or {}, "smoke": release_package_smoke or {}}))
            elif cid == "release_diagnostics":
                ok = bool(release_metadata.get("version"))
                post_rows.append(_check_row(check_id=cid, label=label, required=required, ok=ok, detail=str(release_metadata.get("display") or "release diagnostics missing"), source_path=str(release_metadata.get("metadata_path") or ""), payload=release_metadata))
            elif cid == "restore_diagnostics":
                ok = bool(restore_report_path)
                post_rows.append(_check_row(check_id=cid, label=label, required=required, ok=ok, detail=restore_report_path or "restore diagnostics not found", source_path=restore_report_path, payload=_read_json_if_exists(Path(restore_report_path)) if restore_report_path else {}))
            elif cid == "operational_rollout_policy":
                policy_obj = load_operational_rollout_gates_policy(project_root=project_root_path)
                ok = bool(policy_obj.get("path"))
                detail = str(latest_rollout or policy_obj.get("path") or "operational rollout diagnostics not found")
                post_rows.append(_check_row(check_id=cid, label=label, required=required, ok=ok, detail=detail, source_path=str(latest_rollout or policy_obj.get("path") or ""), payload={"policy": policy_obj, "latest_report": _read_json_if_exists(latest_rollout)}))
            elif cid == "competitive_acceptance_policy":
                policy_obj = load_competitive_acceptance_policy(project_root=project_root_path)
                ok = bool(policy_obj.get("path"))
                detail = str(latest_competitive or policy_obj.get("path") or "competitive acceptance diagnostics not found")
                post_rows.append(_check_row(check_id=cid, label=label, required=required, ok=ok, detail=detail, source_path=str(latest_competitive or policy_obj.get("path") or ""), payload={"policy": policy_obj, "latest_report": _read_json_if_exists(latest_competitive)}))

        pre_ok, pre_failures = _evaluate_required_checks(pre_rows)
        post_ok, post_failures = _evaluate_required_checks(post_rows)
        backup_ready = bool((backup_result or {}).get("ok"))
        rollback_ready = bool(restore_summary_ok)

        triggered: list[dict[str, Any]] = []
        if not backup_ready:
            triggered.append({"criterion_id": "missing_pre_upgrade_backup", "reason": "pre_upgrade_backup_preview_not_ready"})
        if restore_drill_enabled and not rollback_ready:
            triggered.append({"criterion_id": "restore_drill_failed", "reason": "restore_drill_not_ok"})
        if release_package_enabled and not bool((release_package_smoke or {}).get("ok")):
            triggered.append({"criterion_id": "release_package_smoke_failed", "reason": "release_package_smoke_not_ok"})
        if not bool(startup.get("permission_matrix_version")):
            triggered.append({"criterion_id": "startup_bundle_invalid", "reason": "startup_bundle_invalid"})
        if not bool(release_notes.get("ok")):
            triggered.append({"criterion_id": "release_notes_missing", "reason": "release_notes_missing"})

        summary = {
            "pre_upgrade_ok": pre_ok,
            "post_upgrade_ok": post_ok,
            "backup_ready": backup_ready,
            "rollback_ready": rollback_ready,
            "upgrade_ready": bool(pre_ok and post_ok and backup_ready and rollback_ready),
            "rollback_recommended": bool(triggered),
            "critical_failures_count": sum(1 for item in triggered if item.get("criterion_id") != "release_notes_missing"),
            "statement": "Repeatable pre-upgrade checks, backup/restore proof and post-upgrade verification are now collected into one governed report. This is an upgrade discipline contour, not a blanket promise that every customer environment is rollout-safe without evidence.",
        }

        report = {
            "schema": "genomeai.customer_upgrade_report.v1",
            "generated_at": _utc_now(),
            "run_id": run_id,
            "project_root": str(project_root_path),
            "artifacts_root": str(artifacts_root_path),
            "web_storage": str(web_storage_path),
            "db_path": str(db_path_obj),
            "policy": {"path": policy.get("path"), "version": policy.get("version")},
            "summary": summary,
            "release": {
                "metadata": release_metadata,
                "notes": release_notes,
            },
            "pre_upgrade_checks": pre_rows,
            "post_upgrade_checks": post_rows,
            "artifacts": {
                "support_bundle": support_bundle_result or {},
                "backup_preview": backup_result or {},
                "restore_drill": restore_result or {},
                "release_package": release_package_result or {},
                "release_package_smoke": release_package_smoke or {},
            },
            "diagnostics_linkage": {
                "latest_restore_report": str(latest_restore) if latest_restore else None,
                "latest_operational_rollout_report": str(latest_rollout) if latest_rollout else None,
                "latest_competitive_acceptance_report": str(latest_competitive) if latest_competitive else None,
            },
            "rollback": {
                "criteria": policy.get("rollback_criteria") or [],
                "triggered": triggered,
            },
            "manual_checklist": list(policy.get("manual_checklist") or []),
            "report_json_path": str(report_json_path),
            "report_md_path": str(report_md_path),
        }

        report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, cls=_PathEncoder) + "\n", encoding="utf-8")
        report_md_path.write_text(_render_markdown(report), encoding="utf-8")
        _write_best_effort_audit(
            db_path=db_path_obj,
            action="upgrade.discipline.complete",
            object_id=run_id,
            after={
                "report_json_path": str(report_json_path),
                "upgrade_ready": report["summary"]["upgrade_ready"],
                "rollback_recommended": report["summary"]["rollback_recommended"],
            },
        )
        return report
    except Exception as exc:
        _write_best_effort_audit(
            db_path=db_path_obj,
            action="upgrade.discipline.failed",
            object_id=run_id,
            status="ERROR",
            error=str(exc),
            after={"report_root": str(root), "policy_path": policy.get("path")},
        )
        raise


__all__ = [
    "CustomerUpgradeDisciplineError",
    "build_customer_upgrade_report",
    "load_customer_upgrade_policy",
    "load_release_notes",
]

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.infra import ArtifactsRepo, ConnectorRunsRepo
from genomeai.connectors_v1 import (
    connector_health_snapshot,
    connector_retry_policy,
    cron_matches,
    dataset_contract_name,
    failed_dataset_keys_from_results,
    load_connector_spec,
    load_connector_specs,
    planned_output_targets,
    schedule_slot_for,
    summarize_output_targets,
)

from core.audit.events import write_audit
from core.infra.web_db import create_job, get_settings, utcnow_iso


CONNECTOR_RUN_STATUSES = ("running", "success", "partial", "failed", "noop", "stub")


def load_connector_specs_safe(configs_dir: Path, *, project_root: Path) -> tuple[list[Any], list[dict[str, Any]]]:
    specs: list[Any] = []
    errors: list[dict[str, Any]] = []
    configs_dir = configs_dir.resolve()
    if not configs_dir.exists():
        return specs, errors
    for path in sorted(configs_dir.glob("*.y*ml")):
        try:
            specs.append(load_connector_spec(path, project_root=project_root))
        except Exception as e:
            errors.append(
                {
                    "connector_id": path.stem,
                    "kind": "invalid",
                    "enabled": False,
                    "schedule": None,
                    "source_dir": None,
                    "description": None,
                    "config_path": str(path),
                    "schedule_state": {},
                    "health": {
                        "status": "failed",
                        "status_reason": f"{type(e).__name__}: {e}",
                        "required_total": 0,
                        "required_ready": 0,
                        "missing_required": [],
                        "delta_summary": {"total": 0, "new": 0, "changed": 0, "unchanged": 0, "missing": 0, "error": 0, "ready_now": 0},
                        "next_due": None,
                        "next_due_slots": [],
                        "binding_rows": [],
                    },
                    "config_error": str(e),
                }
            )
    return specs, errors


def ensure_connector_tables(conn) -> None:
    ConnectorRunsRepo(conn).ensure_tables()


def _decode_run_row(row: Any) -> dict[str, Any]:
    return ConnectorRunsRepo.decode_run_row(row) or {}


def _parse_job_argv(argv: list[str] | None) -> dict[str, Any]:
    argv = list(argv or [])
    out: dict[str, Any] = {'argv': argv, 'dataset_keys': []}
    idx = 0
    while idx < len(argv):
        token = str(argv[idx])
        if token == '--config' and idx + 1 < len(argv):
            out['config_path'] = argv[idx + 1]
            idx += 2
            continue
        if token == '--connector-run-id' and idx + 1 < len(argv):
            out['connector_run_id'] = argv[idx + 1]
            idx += 2
            continue
        if token == '--trigger' and idx + 1 < len(argv):
            out['trigger_type'] = argv[idx + 1]
            idx += 2
            continue
        if token == '--datasets' and idx + 1 < len(argv):
            out['dataset_keys'] = [str(x).strip().lower() for x in str(argv[idx + 1]).split(',') if str(x).strip()]
            idx += 2
            continue
        if token == '--retry-parent-run-id' and idx + 1 < len(argv):
            out['retry_parent_run_id'] = argv[idx + 1]
            idx += 2
            continue
        if token == '--retry-attempt-no' and idx + 1 < len(argv):
            try:
                out['retry_attempt_no'] = int(argv[idx + 1])
            except Exception:
                out['retry_attempt_no'] = 0
            idx += 2
            continue
        if token == '--scheduled-slot' and idx + 1 < len(argv):
            out['scheduled_slot'] = argv[idx + 1]
            idx += 2
            continue
        if token == '--force':
            out['force'] = True
            idx += 1
            continue
        idx += 1
    return out


def retryable_failed_dataset_keys_from_run(run: dict[str, Any] | None) -> list[str]:
    if not run:
        return []
    outputs = dict((run or {}).get('outputs') or {})
    dataset_results = list(outputs.get('dataset_results') or [])
    keys = failed_dataset_keys_from_results(dataset_results)
    if keys:
        return keys
    return [str(x).strip().lower() for x in (outputs.get('failed_dataset_keys') or []) if str(x).strip()]


def _safe_artifact_download_path(raw_path: str | None, *, artifacts_root: Path) -> str | None:
    if not raw_path:
        return None
    try:
        p = Path(str(raw_path)).resolve()
        rel = p.relative_to(artifacts_root.resolve())
    except Exception:
        return None
    return f"artifacts/{rel.as_posix()}"


def _read_json_file(path: Path) -> dict[str, Any] | None:
    settings = get_settings()
    repo = ArtifactsRepo(settings.project_root, settings.artifacts_root, settings.storage_dir)
    try:
        return repo.read_json(path)
    except Exception:
        return None


def _read_jsonl_objects(path: Path | None, *, limit: int = 200) -> list[dict[str, Any]]:
    settings = get_settings()
    repo = ArtifactsRepo(settings.project_root, settings.artifacts_root, settings.storage_dir)
    return repo.read_jsonl_objects(path, limit=limit)



def _legacy_validation_issue_message(message: str) -> str:
    msg = str(message or '').strip()
    if 'типу bool' in msg:
        return "Failed to coerce value to type 'bool'"
    if 'типу date' in msg:
        return "Failed to coerce value to type 'date'"
    return msg or 'Unknown ingest error'


def _validation_issues_to_legacy_rows(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in issues or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        row['message'] = _legacy_validation_issue_message(row.get('message'))
        rows.append(row)
    return rows

def _summarize_ingest_errors(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_field: dict[str, int] = {}
    by_message: dict[str, int] = {}
    examples: list[dict[str, Any]] = []
    for item in rows:
        field = str(item.get('target_field') or item.get('source_column') or '—')
        message = str(item.get('message') or 'Unknown ingest error')
        by_field[field] = by_field.get(field, 0) + 1
        by_message[message] = by_message.get(message, 0) + 1
        if len(examples) < 5:
            examples.append({
                'row': item.get('row'),
                'target_field': item.get('target_field') or item.get('source_column'),
                'message': item.get('message'),
                'sample_value': item.get('sample_value'),
            })
    return {
        'total': len(rows),
        'by_field': sorted(({'field': k, 'count': v} for k, v in by_field.items()), key=lambda x: (-int(x['count']), x['field'])),
        'by_message': sorted(({'message': k, 'count': v} for k, v in by_message.items()), key=lambda x: (-int(x['count']), x['message'])),
        'examples': examples,
    }


def _build_run_output_targets(*, run: dict[str, Any], selected_files: list[dict[str, Any]], ingest_summaries: list[dict[str, Any]], dataset_results: list[dict[str, Any]], state_after: dict[str, Any] | None, artifacts_root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    by_summary = {str((row or {}).get('dataset_key') or '').strip().lower(): (row or {}) for row in ingest_summaries if str((row or {}).get('dataset_key') or '').strip()}
    by_result = {str((row or {}).get('dataset_key') or '').strip().lower(): (row or {}) for row in dataset_results if str((row or {}).get('dataset_key') or '').strip()}
    state_after = state_after or {}
    active_version = str(run.get('data_version') or state_after.get('last_data_version') or '').strip() or None
    for item in selected_files or []:
        dataset_key = str((item or {}).get('dataset_key') or '').strip().lower()
        if not dataset_key:
            continue
        summary = by_summary.get(dataset_key) or {}
        ds_result = by_result.get(dataset_key) or {}
        dataset_name = str(summary.get('dataset') or ds_result.get('contract_name') or dataset_contract_name(dataset_key) or '')
        target = planned_output_targets(dataset_key=dataset_key, out_version=active_version or 'unknown', artifacts_root=artifacts_root) if active_version else None
        error_path = Path(str(target['error_log_jsonl'])) if target else None
        error_rows = _read_jsonl_objects(error_path)
        validation_report = _read_json_file(Path(str(ds_result.get('validation_errors_json')))) if ds_result.get('validation_errors_json') else None
        if not error_rows and isinstance(validation_report, dict):
            error_rows = _validation_issues_to_legacy_rows(list(validation_report.get('issues') or []))
        breakdown = _summarize_ingest_errors(error_rows)
        result_status = str(ds_result.get('status') or '').strip().lower()
        if summary or result_status == 'written':
            output_status = 'written'
            output_reason = str(ds_result.get('result_reason') or 'ingest summary was recorded for this dataset')
        elif result_status == 'failed':
            output_status = 'failed_dataset'
            output_reason = str(ds_result.get('error_text') or ds_result.get('result_reason') or 'dataset ingest failed')
        elif result_status == 'not_written_noop' or str(run.get('status') or '').strip().lower() == 'noop':
            output_status = 'not_written_noop'
            output_reason = str(ds_result.get('result_reason') or 'connector run skipped ingest because increment state was noop')
        elif str(run.get('status') or '').strip().lower() == 'failed':
            output_status = 'failed_before_write'
            output_reason = 'connector run failed before ingest summary was written for this dataset'
        else:
            output_status = 'planned_only'
            output_reason = str(ds_result.get('result_reason') or 'dataset was selected but no ingest summary is available')
        validation_report_raw = str(ds_result.get('validation_errors_json') or '') or None
        validation_report_download_path = _safe_artifact_download_path(validation_report_raw, artifacts_root=artifacts_root) if validation_report_raw else None
        contract_dataset = dataset_name or None
        contract_href = f"/contracts?focus={contract_dataset}#{contract_dataset}" if contract_dataset else '/contracts'
        validation_report_href = None
        if validation_report_download_path and contract_dataset:
            validation_report_href = (
                f"/contracts/validation-report?path={validation_report_download_path}"
                f"&dataset={contract_dataset}&source=connector&data_version={active_version or ''}"
            )
        outputs.append({
            'dataset_key': dataset_key,
            'dataset': contract_dataset,
            'source_file': item.get('file_path'),
            'mapping_path': item.get('mapping_path'),
            'out_version': active_version,
            'canonical_csv': str(summary.get('canonical_csv') or ds_result.get('canonical_csv') or (target or {}).get('canonical_csv') or '') or None,
            'canonical_parquet': str(summary.get('canonical_parquet') or ds_result.get('canonical_parquet') or (target or {}).get('canonical_parquet') or '') or None,
            'ingest_summary_json': str((target or {}).get('ingest_summary_json') or '') or None,
            'ingest_manifest_json': str((target or {}).get('ingest_manifest_json') or '') or None,
            'error_log_jsonl': str((target or {}).get('error_log_jsonl') or '') or None,
            'rows_in': summary.get('rows_in', ds_result.get('rows_in')),
            'rows_out': summary.get('rows_out', ds_result.get('rows_out')),
            'error_count': summary.get('error_count', ds_result.get('error_count', breakdown['total'])),
            'error_breakdown': breakdown,
            'output_status': output_status,
            'output_reason': output_reason,
            'dataset_result_status': result_status or None,
            'dataset_error_type': ds_result.get('error_type'),
            'dataset_error_text': ds_result.get('error_text'),
            'contract_href': contract_href,
            'validation_report_path': validation_report_raw,
            'validation_report_download_path': validation_report_download_path,
            'validation_report_href': validation_report_href,
            'validation_error_count': ds_result.get('validation_error_count'),
            'validation_preview': list(ds_result.get('validation_preview') or []),
        })
    summary = {
        'total': len(outputs),
        'written': sum(1 for r in outputs if r.get('output_status') == 'written'),
        'not_written_noop': sum(1 for r in outputs if r.get('output_status') == 'not_written_noop'),
        'failed_before_write': sum(1 for r in outputs if r.get('output_status') == 'failed_before_write'),
        'failed_dataset': sum(1 for r in outputs if r.get('output_status') == 'failed_dataset'),
        'planned_only': sum(1 for r in outputs if r.get('output_status') == 'planned_only'),
        'datasets_with_errors': sum(1 for r in outputs if int((r.get('error_breakdown') or {}).get('total') or 0) > 0 or r.get('output_status') == 'failed_dataset'),
        'total_error_examples': sum(int((r.get('error_breakdown') or {}).get('total') or 0) for r in outputs),
        'retryable_failed': sum(1 for r in outputs if r.get('output_status') == 'failed_dataset'),
    }
    return outputs, summary

def build_connector_run_view(run: dict[str, Any], *, artifacts_root: Path) -> dict[str, Any]:
    outputs = dict(run.get("outputs") or {})
    manifest_path_raw = outputs.get("manifest_json")
    state_path_raw = outputs.get("state_json") or outputs.get('state_path')
    manifest_download_path = _safe_artifact_download_path(manifest_path_raw, artifacts_root=artifacts_root)
    state_download_path = _safe_artifact_download_path(state_path_raw, artifacts_root=artifacts_root)
    manifest: dict[str, Any] | None = None
    state_after: dict[str, Any] | None = None
    if manifest_path_raw:
        manifest = _read_json_file(Path(str(manifest_path_raw)))
    if state_path_raw:
        state_after = _read_json_file(Path(str(state_path_raw)))
    selected_files = list((manifest or {}).get("selected_files") or run.get("selected_files") or [])
    ingest_summaries = list((manifest or {}).get("ingest_summaries") or run.get("ingest_summaries") or [])
    dataset_results = list((manifest or {}).get("dataset_results") or outputs.get('dataset_results') or [])
    output_targets, output_summary = _build_run_output_targets(
        run=run,
        selected_files=selected_files,
        ingest_summaries=ingest_summaries,
        dataset_results=dataset_results,
        state_after=state_after,
        artifacts_root=artifacts_root,
    )
    failed_dataset_keys = retryable_failed_dataset_keys_from_run({'outputs': {'dataset_results': dataset_results, 'failed_dataset_keys': outputs.get('failed_dataset_keys')}})
    connector_auto_retry = outputs.get('connector_auto_retry') or None
    if isinstance(connector_auto_retry, dict):
        connector_auto_retry = {
            **connector_auto_retry,
            'reason_text': humanize_recovery_reason(connector_auto_retry.get('reason')),
        }
    return {
        **run,
        "outputs": outputs,
        "manifest": manifest,
        "manifest_download_path": manifest_download_path,
        "state_json_path": str(state_path_raw or "") or None,
        "state_download_path": state_download_path,
        "state_after": state_after,
        "selected_files": selected_files,
        "ingest_summaries": ingest_summaries,
        "dataset_results": dataset_results,
        "failed_dataset_keys": failed_dataset_keys,
        "retryable_failed_datasets": failed_dataset_keys,
        "requested_dataset_keys": list((manifest or {}).get('requested_dataset_keys') or outputs.get('requested_dataset_keys') or []),
        "retry_attempt_no": int(outputs.get('retry_attempt_no') or 0),
        "retry_parent_run_id": str(outputs.get('retry_parent_run_id') or "") or None,
        "connector_auto_retry": connector_auto_retry,
        "output_targets": output_targets,
        "output_summary": output_summary,
        "increment_reason": str((manifest or {}).get("increment_reason") or "") or None,
        "created_at_utc": str((manifest or {}).get("created_at_utc") or "") or None,
    }


def summarize_connector_runs(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any] | None]:
    summary: dict[str, dict[str, Any] | None] = {
        "last_success": None,
        "last_failed": None,
        "last_partial": None,
        "last_noop": None,
        "last_stub": None,
        "last_any": runs[0] if runs else None,
    }
    for row in runs:
        status = str(row.get("status") or "").strip().lower()
        if status == "success" and summary["last_success"] is None:
            summary["last_success"] = row
        elif status == "partial" and summary["last_partial"] is None:
            summary["last_partial"] = row
        elif status == "failed" and summary["last_failed"] is None:
            summary["last_failed"] = row
        elif status == "noop" and summary["last_noop"] is None:
            summary["last_noop"] = row
        elif status == "stub" and summary["last_stub"] is None:
            summary["last_stub"] = row
    return summary


def enrich_binding_rows_with_run_history(bindings: list[dict[str, Any]], runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history: dict[str, dict[str, Any]] = {}
    connector_last_failed = next((r for r in runs if str(r.get("status") or "").strip().lower() == "failed"), None)
    for row in runs:
        status = str(row.get("status") or "").strip().lower()
        for item in row.get("selected_files") or []:
            dataset_key = str((item or {}).get("dataset_key") or "").strip().lower()
            if not dataset_key:
                continue
            info = history.setdefault(dataset_key, {
                "last_seen_run_id": None,
                "last_seen_status": None,
                "last_success_run_id": None,
                "last_success_data_version": None,
                "last_noop_run_id": None,
            })
            if info["last_seen_run_id"] is None:
                info["last_seen_run_id"] = row.get("connector_run_id")
                info["last_seen_status"] = row.get("status")
            if status == "success" and info["last_success_run_id"] is None:
                info["last_success_run_id"] = row.get("connector_run_id")
                info["last_success_data_version"] = row.get("data_version")
            elif status == "noop" and info["last_noop_run_id"] is None:
                info["last_noop_run_id"] = row.get("connector_run_id")

    out: list[dict[str, Any]] = []
    for row in bindings or []:
        dataset_key = str((row or {}).get("dataset_key") or "").strip().lower()
        info = history.get(dataset_key) or {}
        merged = dict(row)
        merged["last_seen_run_id"] = info.get("last_seen_run_id")
        merged["last_seen_status"] = info.get("last_seen_status")
        merged["last_success_run_id"] = info.get("last_success_run_id")
        merged["last_success_data_version"] = info.get("last_success_data_version")
        merged["last_noop_run_id"] = info.get("last_noop_run_id")
        merged["connector_last_failed_run_id"] = connector_last_failed.get("connector_run_id") if connector_last_failed else None
        out.append(merged)
    return out


def start_connector_run(
    conn,
    *,
    tenant_id: str,
    connector_run_id: str,
    connector_id: str,
    kind: str,
    trigger_type: str,
    schedule_slot: str | None,
    config_path: str,
) -> None:
    ts = utcnow_iso()
    ConnectorRunsRepo(conn).start_run(
        tenant_id=tenant_id,
        connector_run_id=connector_run_id,
        connector_id=connector_id,
        kind=kind,
        trigger_type=trigger_type,
        schedule_slot=schedule_slot,
        config_path=config_path,
        started_at=ts,
    )


def finish_connector_run(
    conn,
    *,
    tenant_id: str,
    connector_run_id: str,
    status: str,
    data_version: str | None,
    message: str,
    outputs: dict[str, Any],
    selected_files: list[dict[str, Any]],
    ingest_summaries: list[dict[str, Any]],
    error_text: str | None = None,
) -> None:
    ConnectorRunsRepo(conn).finish_run(
        tenant_id=tenant_id,
        connector_run_id=connector_run_id,
        status=status,
        finished_at=utcnow_iso(),
        data_version=data_version,
        message=message,
        outputs=outputs,
        selected_files=selected_files,
        ingest_summaries=ingest_summaries,
        error_text=error_text,
    )


def get_connector_run(conn, *, tenant_id: str, connector_run_id: str) -> dict[str, Any] | None:
    return ConnectorRunsRepo(conn).get_run(tenant_id=tenant_id, connector_run_id=connector_run_id)


def list_connector_runs(conn, *, tenant_id: str, connector_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    return ConnectorRunsRepo(conn).list_runs(tenant_id=tenant_id, connector_id=connector_id, limit=limit)


def latest_retryable_run(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in runs or []:
        if retryable_failed_dataset_keys_from_run(row):
            return row
    return None


def humanize_recovery_reason(reason: str | None) -> str:
    raw = str(reason or '').strip()
    if not raw:
        return '—'
    if raw == 'auto_retry_disabled':
        return 'auto retry disabled in connector policy'
    if raw == 'max_attempts_reached':
        return 'max retry attempts reached for failed dataset subset'
    if raw.startswith('status_not_retryable:'):
        return f"connector status '{raw.split(':', 1)[1] or 'unknown'}' is not included in retry_on_statuses"
    if raw.startswith('queue_guardrail:'):
        return f"recovery queue guardrail blocked scheduling ({raw.split(':', 1)[1] or 'guardrail'})"
    if raw == 'failed_dataset_subset':
        return 'failed dataset subset retry was scheduled'
    return raw


def latest_recovery_decision(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for row in runs or []:
        outputs = dict((row or {}).get('outputs') or {})
        ctx = outputs.get('connector_auto_retry') or {}
        if not isinstance(ctx, dict) or not ctx:
            continue
        failed_dataset_keys = [str(x).strip().lower() for x in (ctx.get('failed_dataset_keys') or []) if str(x).strip()]
        return {
            'connector_run_id': row.get('connector_run_id'),
            'run_status': row.get('status'),
            'decision_status': str(ctx.get('status') or '').strip() or None,
            'reason': str(ctx.get('reason') or '').strip() or None,
            'reason_text': humanize_recovery_reason(ctx.get('reason')),
            'failed_dataset_keys': failed_dataset_keys,
            'retry_job_id': ctx.get('retry_job_id'),
            'next_attempt_at': ctx.get('next_attempt_at'),
            'retry_attempt_no': int(ctx.get('retry_attempt_no') or 0),
            'error': str(ctx.get('error') or '').strip() or None,
        }
    return None


def normalize_dataset_keys(dataset_keys: list[str] | None) -> list[str]:
    return sorted(dict.fromkeys(str(k).strip().lower() for k in (dataset_keys or []) if str(k).strip()))


def is_recovery_trigger(trigger_type: str | None) -> bool:
    return str(trigger_type or '').strip().lower() in {'retry_failed', 'retry_last_failed', 'auto_retry_failed'}


def summarize_recovery_analytics(runs: list[dict[str, Any]], pending_recovery_jobs: list[dict[str, Any]], *, queue_limit: int) -> dict[str, Any]:
    stats = {
        'queue_limit': int(queue_limit or 1),
        'pending_jobs': 0,
        'pending_datasets': 0,
        'retryable_runs': 0,
        'auto_retry_runs': 0,
        'manual_retry_runs': 0,
        'recovered_successes': 0,
        'partial_or_failed_runs': 0,
        'success_rate_pct': 0,
        'last_recovery_trigger': None,
        'last_recovery_run_id': None,
        'last_recovery_status': None,
    }
    stats['pending_jobs'] = len(pending_recovery_jobs or [])
    pending_datasets = set()
    for job in pending_recovery_jobs or []:
        if is_recovery_trigger(job.get('trigger_type')):
            for ds in job.get('dataset_keys') or []:
                pending_datasets.add(str(ds).strip().lower())
    stats['pending_datasets'] = len(pending_datasets)
    recovery_runs_total = 0
    for row in runs or []:
        failed_keys = retryable_failed_dataset_keys_from_run(row)
        if failed_keys:
            stats['retryable_runs'] += 1
        status = str(row.get('status') or '').strip().lower()
        trigger = str(row.get('trigger_type') or '').strip().lower()
        if status in {'partial', 'failed'}:
            stats['partial_or_failed_runs'] += 1
        if is_recovery_trigger(trigger):
            recovery_runs_total += 1
            if trigger == 'auto_retry_failed':
                stats['auto_retry_runs'] += 1
            else:
                stats['manual_retry_runs'] += 1
            if stats['last_recovery_run_id'] is None:
                stats['last_recovery_run_id'] = row.get('connector_run_id')
                stats['last_recovery_trigger'] = trigger
                stats['last_recovery_status'] = status
            if status == 'success':
                stats['recovered_successes'] += 1
    if recovery_runs_total:
        stats['success_rate_pct'] = int(round(100 * stats['recovered_successes'] / max(1, recovery_runs_total)))
    return stats


def find_duplicate_recovery_job(conn, *, tenant_id: str, config_path: str, dataset_keys: list[str] | None, retry_parent_run_id: str | None) -> dict[str, Any] | None:
    normalized_dataset_keys = normalize_dataset_keys(dataset_keys)
    normalized_parent = str(retry_parent_run_id or '').strip() or None
    for job in list_connector_pending_jobs(conn, tenant_id=tenant_id, config_path=config_path, limit=200):
        if not is_recovery_trigger(job.get('trigger_type')):
            continue
        if normalize_dataset_keys(job.get('dataset_keys') or []) != normalized_dataset_keys:
            continue
        job_parent = str(job.get('retry_parent_run_id') or '').strip() or None
        if job_parent != normalized_parent:
            continue
        return job
    return None


def enforce_recovery_queue_guardrails(conn, *, tenant_id: str, config_path: str, connector_id: str, dataset_keys: list[str] | None, retry_parent_run_id: str | None, queue_limit: int) -> None:
    pending = list_connector_pending_jobs(conn, tenant_id=tenant_id, config_path=config_path, limit=max(50, int(queue_limit or 1) * 10))
    recovery_pending = [job for job in pending if is_recovery_trigger(job.get('trigger_type'))]
    duplicate = find_duplicate_recovery_job(conn, tenant_id=tenant_id, config_path=config_path, dataset_keys=dataset_keys, retry_parent_run_id=retry_parent_run_id)
    if duplicate:
        datasets = ','.join(normalize_dataset_keys(dataset_keys)) or '—'
        raise ValueError(
            f"Recovery job already queued for connector={connector_id} datasets={datasets}"
            f" retry_parent_run_id={str(retry_parent_run_id or '—')} job_id={duplicate.get('public_job_id') or duplicate.get('job_id')}"
        )
    if len(recovery_pending) >= max(1, int(queue_limit or 1)):
        raise ValueError(
            f"Recovery queue limit reached for connector={connector_id}: {len(recovery_pending)}/{max(1, int(queue_limit or 1))} queued recovery jobs"
        )


def list_connector_pending_jobs(conn, *, tenant_id: str, config_path: str, limit: int = 25) -> list[dict[str, Any]]:
    return ConnectorRunsRepo(conn).list_pending_jobs(tenant_id=tenant_id, config_path=config_path, limit=limit, parser=_parse_job_argv)


def get_schedule_state(conn, *, tenant_id: str, connector_id: str) -> dict[str, Any] | None:
    return ConnectorRunsRepo(conn).get_schedule_state(tenant_id=tenant_id, connector_id=connector_id)


def set_schedule_state(conn, *, tenant_id: str, connector_id: str, last_slot: str, last_job_id: int | None) -> None:
    ConnectorRunsRepo(conn).set_schedule_state(tenant_id=tenant_id, connector_id=connector_id, last_slot=last_slot, last_job_id=last_job_id, last_enqueued_at=utcnow_iso())


def enqueue_connector_job(
    conn,
    *,
    tenant_id: str,
    user_id: int,
    username: str,
    config_path: str,
    trigger_type: str,
    schedule_slot: str | None = None,
    force: bool = False,
    dataset_keys: list[str] | None = None,
    next_attempt_at: str | None = None,
    retry_source: str | None = None,
    retry_parent_run_id: str | None = None,
    retry_attempt_no: int = 0,
) -> tuple[int, dict[str, Any]]:
    settings = get_settings()
    project_root = settings.project_root
    spec = load_connector_spec(Path(config_path), project_root=project_root)
    connector_run_id = f"connrun_{uuid.uuid4().hex[:12]}"
    log_path = settings.logs_dir / f"connector_{spec.connector_id}_{uuid.uuid4().hex[:8]}.log"
    argv = [
        "connectors",
        "run",
        "--config",
        str(Path(config_path).resolve()),
        "--artifacts",
        str(settings.artifacts_root),
        "--trigger",
        trigger_type,
        "--connector-run-id",
        connector_run_id,
    ]
    if schedule_slot:
        argv += ["--scheduled-slot", schedule_slot]
    normalized_dataset_keys = normalize_dataset_keys(dataset_keys)
    if normalized_dataset_keys:
        argv += ["--datasets", ",".join(normalized_dataset_keys)]
    if retry_parent_run_id:
        argv += ["--retry-parent-run-id", str(retry_parent_run_id)]
    if int(retry_attempt_no or 0) > 0:
        argv += ["--retry-attempt-no", str(int(retry_attempt_no or 0))]
    if force:
        argv += ["--force"]
    normalized_next_attempt_at = str(next_attempt_at).strip() if next_attempt_at is not None else None
    normalized_retry_source = str(retry_source).strip() if retry_source is not None else None
    normalized_retry_parent = str(retry_parent_run_id).strip() if retry_parent_run_id is not None else None
    if is_recovery_trigger(trigger_type) and normalized_dataset_keys:
        enforce_recovery_queue_guardrails(
            conn,
            tenant_id=tenant_id,
            config_path=str(Path(config_path).resolve()),
            connector_id=spec.connector_id,
            dataset_keys=normalized_dataset_keys,
            retry_parent_run_id=normalized_retry_parent,
            queue_limit=get_settings().connector_recovery_queue_limit,
        )
    job_id = create_job(
        conn,
        kind="connector_run",
        tenant_id=tenant_id,
        user_id=user_id,
        user=username,
        command="python -m genomeai",
        args={"argv": argv},
        log_path=log_path,
        next_attempt_at=normalized_next_attempt_at or None,
        retry_source=normalized_retry_source or None,
    )
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=user_id,
        username=username,
        role="system" if user_id == 0 else "Operator",
        action="connector.enqueue",
        object_type="connector",
        object_id=spec.connector_id,
        after={
            "config_path": str(Path(config_path).resolve()),
            "connector_run_id": connector_run_id,
            "trigger_type": trigger_type,
            "schedule_slot": schedule_slot,
            "job_id": job_id,
            "force": bool(force),
            "dataset_keys": normalized_dataset_keys,
            "next_attempt_at": normalized_next_attempt_at or None,
            "retry_source": normalized_retry_source or None,
            "retry_parent_run_id": normalized_retry_parent or None,
            "retry_attempt_no": int(retry_attempt_no or 0),
        },
        status="OK",
    )
    return job_id, {
        "connector_id": spec.connector_id,
        "kind": spec.kind,
        "connector_run_id": connector_run_id,
        "schedule_slot": schedule_slot,
        "config_path": str(Path(config_path).resolve()),
        "next_attempt_at": normalized_next_attempt_at or None,
        "retry_source": normalized_retry_source or None,
        "retry_parent_run_id": normalized_retry_parent or None,
        "retry_attempt_no": int(retry_attempt_no or 0),
        "dataset_keys": normalized_dataset_keys,
    }


def schedule_due_connector_jobs(
    conn,
    *,
    tenant_id: str,
    user_id: int,
    username: str,
    configs_dir: Path,
    when: datetime,
) -> dict[str, Any]:
    ensure_connector_tables(conn)
    settings = get_settings()
    project_root = settings.project_root
    when = when.astimezone(timezone.utc).replace(second=0, microsecond=0)
    slot = schedule_slot_for(when)
    enqueued: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    specs, errors = load_connector_specs_safe(configs_dir, project_root=project_root)
    for spec in specs:
        if not spec.enabled:
            skipped.append({"connector_id": spec.connector_id, "reason": "disabled"})
            continue
        if not spec.schedule:
            skipped.append({"connector_id": spec.connector_id, "reason": "no_schedule"})
            continue
        if not cron_matches(spec.schedule, when):
            skipped.append({"connector_id": spec.connector_id, "reason": "not_due"})
            continue
        state = get_schedule_state(conn, tenant_id=tenant_id, connector_id=spec.connector_id)
        if state and str(state.get("last_slot") or "") == slot:
            skipped.append({"connector_id": spec.connector_id, "reason": "already_enqueued_for_slot", "slot": slot})
            continue
        job_id, meta = enqueue_connector_job(
            conn,
            tenant_id=tenant_id,
            user_id=user_id,
            username=username,
            config_path=str(spec.config_path),
            trigger_type="schedule",
            schedule_slot=slot,
        )
        set_schedule_state(conn, tenant_id=tenant_id, connector_id=spec.connector_id, last_slot=slot, last_job_id=job_id)
        meta["job_id"] = job_id
        enqueued.append(meta)
    skipped.extend({"connector_id": e.get("connector_id"), "reason": "invalid_config", "error": e.get("config_error")} for e in errors)
    write_audit(
        conn,
        tenant_id=tenant_id,
        user_id=user_id,
        username=username,
        role="system" if user_id == 0 else "Operator",
        action="connector.schedule_tick",
        object_type="connector_schedule",
        object_id=slot,
        after={"slot": slot, "enqueued": enqueued, "skipped": skipped, "configs_dir": str(configs_dir.resolve())},
        status="OK",
    )
    return {"slot": slot, "enqueued": enqueued, "skipped": skipped}


def _parse_iso_dt(raw: Any) -> datetime | None:
    value = str(raw or '').strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except Exception:
        return None


def _minutes_between(later: datetime | None, earlier: datetime | None) -> int | None:
    if later is None or earlier is None:
        return None
    delta = later - earlier
    return max(0, int(delta.total_seconds() // 60))


def build_connector_source_status(spec, *, health: dict[str, Any], runs: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(second=0, microsecond=0)
    summary = summarize_connector_runs(runs)
    last_any = summary.get('last_any') or {}
    last_success = summary.get('last_success') or {}
    last_failed = summary.get('last_failed') or {}
    binding_rows = enrich_binding_rows_with_run_history(list(health.get('binding_rows') or []), runs)

    latest_source_dt = None
    latest_source_raw = None
    binding_errors: list[str] = []
    for row in binding_rows:
        raw_ts = row.get('selected_modified_at')
        dt = _parse_iso_dt(raw_ts)
        if dt and (latest_source_dt is None or dt > latest_source_dt):
            latest_source_dt = dt
            latest_source_raw = str(raw_ts)
        err = str(row.get('error') or '').strip()
        if err:
            binding_errors.append(f"{row.get('dataset_key')}: {err}")

    last_pull_dt = _parse_iso_dt(last_any.get('finished_at') or last_any.get('started_at'))
    last_success_dt = _parse_iso_dt(last_success.get('finished_at') or last_success.get('started_at'))
    last_failed_dt = _parse_iso_dt(last_failed.get('finished_at') or last_failed.get('started_at'))

    source_status = 'unknown'
    action_hint = 'Проверьте connector config и diagnostics.'
    if not bool(spec.enabled):
        source_status = 'disabled'
        action_hint = 'Connector отключён; включите его только после проверки source bindings и schedule.'
    elif str(spec.kind or '').strip().lower() in {'api_stub', 'onec_stub'}:
        source_status = 'stub'
        action_hint = 'Это representative stub; настройте реальный export adapter/config для staged interoperability.'
    elif binding_errors:
        source_status = 'source_error'
        action_hint = 'Исправьте source path/pattern или загрузите отсутствующие выгрузки, затем повторите pull.'
    elif list(health.get('missing_required') or []):
        source_status = 'waiting_source'
        action_hint = 'Нужны обязательные выгрузки; проверьте inbox/source_dir и naming conventions.'
    elif list(health.get('pending_bindings') or []):
        source_status = 'refresh_available'
        action_hint = 'Обнаружены новые/изменённые выгрузки; запустите pull now или дождитесь schedule.'
    elif last_success_dt is None:
        source_status = 'never_pulled'
        action_hint = 'Выполните первый connector run и проверьте canonical outputs + contracts.'
    else:
        source_status = 'in_sync'
        action_hint = 'Источник и canonical snapshot согласованы в пределах текущего batch contour.'

    if source_status == 'in_sync' and latest_source_dt is not None:
        source_age = _minutes_between(now, latest_source_dt)
        if source_age is not None and source_age > 24 * 60:
            source_status = 'stale_batch'
            action_hint = 'Последняя выгрузка старая; не используйте как near-real-time и запросите новый batch export.'

    last_error = None
    if binding_errors:
        last_error = '; '.join(binding_errors[:3])
    elif last_failed:
        last_error = str(last_failed.get('error_text') or last_failed.get('message') or '').strip() or None

    freshness = 'unknown'
    source_age_minutes = _minutes_between(now, latest_source_dt)
    if source_age_minutes is not None:
        if source_age_minutes <= 6 * 60:
            freshness = 'fresh'
        elif source_age_minutes <= 24 * 60:
            freshness = 'aging'
        else:
            freshness = 'stale'

    return {
        'source_system': str(spec.raw.get('source_system') or spec.connector_id),
        'system_family': str(spec.raw.get('system_family') or 'farm_system'),
        'export_mode': str(spec.raw.get('export_mode') or ('batch_export' if spec.kind == 'file' else spec.kind)),
        'schedule_hint': str(spec.raw.get('schedule_hint') or '').strip() or None,
        'supported_contracts': [str(dataset_contract_name(b.dataset_key) or '') for b in spec.bindings if dataset_contract_name(b.dataset_key)],
        'source_status': source_status,
        'freshness': freshness,
        'source_export_at': latest_source_raw,
        'source_age_minutes': source_age_minutes,
        'last_pull_at': last_pull_dt.replace(microsecond=0).isoformat() if last_pull_dt else None,
        'last_pull_age_minutes': _minutes_between(now, last_pull_dt),
        'last_pull_status': str(last_any.get('status') or '').strip() or None,
        'last_success_at': last_success_dt.replace(microsecond=0).isoformat() if last_success_dt else None,
        'last_failed_at': last_failed_dt.replace(microsecond=0).isoformat() if last_failed_dt else None,
        'sync_lag_minutes': _minutes_between(last_success_dt, latest_source_dt),
        'last_error': last_error,
        'action_hint': action_hint,
        'binding_rows': binding_rows,
    }


def catalog_with_state(conn, *, tenant_id: str, configs_dir: Path) -> list[dict[str, Any]]:
    settings = get_settings()
    out: list[dict[str, Any]] = []
    specs, errors = load_connector_specs_safe(configs_dir, project_root=settings.project_root)
    now = datetime.now(timezone.utc)
    for spec in specs:
        state = get_schedule_state(conn, tenant_id=tenant_id, connector_id=spec.connector_id) or {}
        previous_state = None
        try:
            from genomeai.connectors_v1 import load_connector_state
            previous_state = load_connector_state(project_root=settings.project_root, connector_id=spec.connector_id)
        except Exception:
            previous_state = None
        health = connector_health_snapshot(spec, project_root=settings.project_root, previous_state=previous_state)
        runs = list_connector_runs(conn, tenant_id=tenant_id, connector_id=spec.connector_id, limit=20)
        source_status = build_connector_source_status(spec, health=health, runs=runs, now=now)
        out.append(
            {
                "connector_id": spec.connector_id,
                "kind": spec.kind,
                "enabled": spec.enabled,
                "schedule": spec.schedule,
                "source_dir": spec.source_dir,
                "description": spec.description,
                "config_path": str(spec.config_path),
                "schedule_state": state,
                "health": health,
                "source_system": source_status.get('source_system'),
                "system_family": source_status.get('system_family'),
                "export_mode": source_status.get('export_mode'),
                "supported_contracts": source_status.get('supported_contracts'),
                "source_status": source_status.get('source_status'),
                "freshness": source_status.get('freshness'),
                "source_export_at": source_status.get('source_export_at'),
                "source_age_minutes": source_status.get('source_age_minutes'),
                "last_pull_at": source_status.get('last_pull_at'),
                "last_pull_age_minutes": source_status.get('last_pull_age_minutes'),
                "last_pull_status": source_status.get('last_pull_status'),
                "last_success_at": source_status.get('last_success_at'),
                "last_failed_at": source_status.get('last_failed_at'),
                "sync_lag_minutes": source_status.get('sync_lag_minutes'),
                "last_error": source_status.get('last_error'),
                "action_hint": source_status.get('action_hint'),
                "binding_rows": source_status.get('binding_rows'),
                "schedule_hint": source_status.get('schedule_hint'),
            }
        )
    out.extend(errors)
    out.sort(key=lambda row: str((row or {}).get("connector_id") or ""))
    return out



def summarize_catalog_health(catalog: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(second=0, microsecond=0)
    summary = {
        "total": len(catalog or []),
        "ready": 0,
        "warning": 0,
        "failed": 0,
        "stub": 0,
        "disabled": 0,
        "due_next_hour": 0,
    }
    deadline = now.timestamp() + 3600
    for row in catalog or []:
        status = str(((row or {}).get("health") or {}).get("status") or "").strip().lower()
        if status in summary:
            summary[status] += 1
        health = (row or {}).get("health") or {}
        due = health.get("next_due")
        if due:
            try:
                ts = datetime.fromisoformat(str(due)).astimezone(timezone.utc).timestamp()
                if now.timestamp() <= ts <= deadline:
                    summary["due_next_hour"] += 1
            except Exception:
                pass
    return summary

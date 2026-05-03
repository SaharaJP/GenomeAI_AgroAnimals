from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.config import MappingSchema, field_spec, load_yaml_mapping, non_empty_string, non_negative_float, positive_int
from core.infra import ArtifactsRepo


JOB_STATUSES = (
    "queued",
    "running",
    "done",
    "failed",
    "cancel_requested",
    "cancelled",
)
ACTIVE_JOB_STATUSES = ("queued", "running", "cancel_requested")
TERMINAL_JOB_STATUSES = {"done", "failed", "cancelled"}
PATH_SUFFIXES = (".csv", ".xlsx", ".json", ".jsonl", ".parquet", ".pdf", ".html", ".zip", ".txt", ".md", ".yaml", ".yml")
PREVIEW_SUFFIXES = (".txt", ".md", ".json", ".jsonl", ".csv", ".html", ".yaml", ".yml", ".log")


@dataclass(frozen=True)
class JobRunnerConfig:
    queue_name_default: str = "default"
    max_attempts_default: int = 1
    cancel_poll_interval_sec: float = 0.5
    cancel_grace_sec: int = 10
    ui_log_tail_bytes: int = 262_144
    ui_auto_refresh_sec: int = 3
    log_stream_chunk_bytes: int = 16_384
    auto_retry_enabled_default: bool = True
    auto_retry_backoff_sec: float = 2.0
    auto_retry_exit_codes: tuple[int, ...] = (1, 2, 124)
    auto_retry_kinds: tuple[str, ...] = ("ingest", "qc", "train", "score", "report", "repro", "pack")


_RUN_KEYS = (
    "report_version",
    "scoring_run",
    "qc_run",
    "model_version",
    "run_id",
    "economics_run",
    "unit_econ_run",
    "roi_run",
    "repro_run",
    "pedigree_run",
    "mating_plan_run",
    "pack_id",
)


def _artifacts_repo_for_project(project_root: Path) -> ArtifactsRepo:
    root = Path(project_root).resolve()
    return ArtifactsRepo(project_root=root, artifacts_root=root / "artifacts", storage_root=root / "storage")


def load_job_runner_config(project_root: Path) -> JobRunnerConfig:
    cfg_path = (project_root / "configs" / "jobs" / "runner_v2.yaml").resolve()
    payload = load_yaml_mapping(
        cfg_path,
        schema=MappingSchema(
            config_name='runner_v2',
            fields=(
                field_spec('queue_name_default', str, default='default', validator=non_empty_string),
                field_spec('max_attempts_default', int, default=1, validator=positive_int),
                field_spec('cancel_poll_interval_sec', (int, float), default=0.5, validator=non_negative_float),
                field_spec('cancel_grace_sec', int, default=10, validator=positive_int),
                field_spec('ui_log_tail_bytes', int, default=262_144, validator=positive_int),
                field_spec('ui_auto_refresh_sec', int, default=3, validator=positive_int),
                field_spec('log_stream_chunk_bytes', int, default=16_384, validator=positive_int),
                field_spec('auto_retry_enabled_default', bool, default=True),
                field_spec('auto_retry_backoff_sec', (int, float), default=2.0, validator=non_negative_float),
                field_spec('auto_retry_exit_codes', list, default=[1, 2, 124], item_type=int),
                field_spec('auto_retry_kinds', list, default=['ingest', 'qc', 'train', 'score', 'report', 'repro', 'pack'], item_type=str),
            ),
        ),
        required=False,
        default={},
    )
    raw_codes = payload.get("auto_retry_exit_codes") or [1, 2, 124]
    raw_kinds = payload.get("auto_retry_kinds") or ["ingest", "qc", "train", "score", "report", "repro", "pack"]
    return JobRunnerConfig(
        queue_name_default=str(payload.get("queue_name_default") or "default"),
        max_attempts_default=max(1, int(payload.get("max_attempts_default") or 1)),
        cancel_poll_interval_sec=max(0.2, float(payload.get("cancel_poll_interval_sec") or 0.5)),
        cancel_grace_sec=max(1, int(payload.get("cancel_grace_sec") or 10)),
        ui_log_tail_bytes=max(8192, int(payload.get("ui_log_tail_bytes") or 262_144)),
        ui_auto_refresh_sec=max(1, int(payload.get("ui_auto_refresh_sec") or 3)),
        log_stream_chunk_bytes=max(1024, int(payload.get("log_stream_chunk_bytes") or 16_384)),
        auto_retry_enabled_default=bool(payload.get("auto_retry_enabled_default", True)),
        auto_retry_backoff_sec=max(0.0, float(payload.get("auto_retry_backoff_sec") or 2.0)),
        auto_retry_exit_codes=tuple(sorted({int(x) for x in raw_codes})),
        auto_retry_kinds=tuple(str(x).strip() for x in raw_kinds if str(x).strip()),
    )


def new_public_job_id() -> str:
    return f"job_{uuid.uuid4().hex[:12]}"


def parse_cli_argv(argv: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    if not argv:
        return out
    out["pipeline_key"] = str(argv[0]).strip()
    i = 1
    while i < len(argv):
        tok = str(argv[i])
        if tok.startswith("--"):
            key = tok[2:].replace("-", "_")
            if i + 1 < len(argv) and not str(argv[i + 1]).startswith("--"):
                out[key] = str(argv[i + 1])
                i += 2
                continue
            out[key] = "true"
        i += 1
    return out


def infer_job_refs(*, kind: str, args: dict[str, Any]) -> dict[str, Any]:
    argv = args.get("argv") or []
    if not isinstance(argv, list):
        argv = []
    parsed = parse_cli_argv([str(x) for x in argv])
    data_version = parsed.get("data_version") or parsed.get("out_version") or args.get("data_version") or args.get("out_version")
    run_id = parsed.get("run_id") or args.get("run_id")
    refs: dict[str, Any] = {
        "pipeline_key": parsed.get("pipeline_key") or str(args.get("pipeline_key") or kind or "job"),
        "data_version": data_version,
        "run_id": run_id,
        "qc_run": parsed.get("qc_run") or args.get("qc_run"),
        "model_version": parsed.get("model_version") or args.get("model_version"),
        "scoring_run": parsed.get("scoring_run") or args.get("scoring_run"),
        "report_version": parsed.get("report_version") or args.get("report_version"),
        "attempt_no": 0,
    }
    for key in _RUN_KEYS:
        if not refs.get("run_id") and parsed.get(key):
            refs["run_id"] = parsed.get(key)
            break
    return refs


def discover_artifacts_from_kv(kv: dict[str, str], *, project_root: Path) -> list[str]:
    found: list[str] = []
    for _k, raw in (kv or {}).items():
        val = str(raw or "").strip()
        if not val:
            continue
        looks_like_path = "/" in val or "\\" in val or val.endswith(PATH_SUFFIXES)
        if not looks_like_path:
            continue
        p = Path(val)
        if not p.is_absolute():
            p = (project_root / p).resolve()
        if not p.exists():
            continue
        try:
            rel = p.relative_to(project_root)
            found.append(str(rel))
        except Exception:
            found.append(str(p))
    uniq: list[str] = []
    seen = set()
    for item in found:
        if item not in seen:
            uniq.append(item)
            seen.add(item)
    return uniq


def clone_retry_args(job: dict[str, Any]) -> dict[str, Any]:
    try:
        args = json.loads(job.get("args_json") or "{}")
    except Exception:
        args = {}
    if not isinstance(args, dict):
        args = {}
    return args


def iso_after_seconds(delay_sec: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(0.0, float(delay_sec or 0.0)))).replace(microsecond=0).isoformat()


def is_auto_retry_allowed(*, cfg: JobRunnerConfig, job: dict[str, Any], exit_code: int, final_status: str) -> bool:
    if final_status != "failed" or not cfg.auto_retry_enabled_default:
        return False
    kind = str(job.get("kind") or job.get("pipeline_key") or "").strip()
    if cfg.auto_retry_kinds and kind not in set(cfg.auto_retry_kinds):
        return False
    if cfg.auto_retry_exit_codes and int(exit_code) not in set(cfg.auto_retry_exit_codes):
        return False
    attempt_no = int(job.get("attempt_no") or 0)
    max_attempts = max(1, int(job.get("max_attempts") or 1))
    return attempt_no + 1 < max_attempts


def _artifact_dir_candidates(job: dict[str, Any], *, artifacts_root: Path) -> list[Path]:
    data_version = str(job.get("data_version") or "").strip()
    if not data_version:
        return []
    base = artifacts_root / data_version
    pairs = [
        ("qc", job.get("qc_run")),
        ("models", job.get("model_version")),
        ("scoring", job.get("scoring_run")),
        ("reports", job.get("report_version")),
        ("whatif_reports", job.get("report_version") if str(job.get("kind") or "") == "whatif_report" else None),
    ]
    out: list[Path] = []
    for folder, ref in pairs:
        ref_s = str(ref or "").strip()
        if ref_s:
            out.append(base / folder / ref_s)
    return out


def discover_job_artifacts(job: dict[str, Any], *, project_root: Path, artifacts_root: Path, kv: dict[str, str] | None = None) -> list[str]:
    repo = ArtifactsRepo(project_root=project_root, artifacts_root=artifacts_root, storage_root=Path(project_root) / "storage")
    found: list[str] = []
    for item in discover_artifacts_from_kv(kv or {}, project_root=project_root):
        if item not in found:
            found.append(item)

    for cand in _artifact_dir_candidates(job, artifacts_root=artifacts_root):
        for fp in repo.list_files_recursive(cand, limit=200):
            try:
                rel = fp.relative_to(project_root)
                val = str(rel)
            except Exception:
                val = str(fp.resolve())
            if val not in found:
                found.append(val)
    return found


def is_previewable_artifact(path: str) -> bool:
    s = str(path or "").lower()
    return s.endswith(PREVIEW_SUFFIXES)


def read_artifact_preview(path: Path, *, max_bytes: int = 65536) -> tuple[str, bool]:
    fp = Path(path).resolve()
    repo = ArtifactsRepo(project_root=fp.parent, artifacts_root=fp.parent, storage_root=fp.parent)
    return repo.read_preview(fp, max_bytes=max_bytes)

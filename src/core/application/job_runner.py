from __future__ import annotations

import contextlib
import io
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO
from uuid import uuid4

from core.infra.web_db import create_job
from core.observability import log_event

PIPELINE_JOB_KEYS: tuple[str, ...] = ("ingest", "qc", "train", "score", "repro", "report", "pack")


@dataclass(frozen=True)
class PipelineJobRequest:
    kind: str
    argv: list[str]
    object_id: str
    command: str = "python -m genomeai"
    extra_after: dict[str, Any] = field(default_factory=dict)
    max_attempts: int | None = None


@dataclass(frozen=True)
class PipelineExecutionResult:
    request: PipelineJobRequest
    exit_code: int
    log_path: str | None
    kv: dict[str, str]



def _sanitize_job_kind(kind: str) -> str:
    return ''.join(ch if ch.isalnum() or ch in {'_', '-'} else '_' for ch in str(kind or 'job')).strip('_') or 'job'



def _parse_cli_argv(argv: list[str]) -> dict[str, str]:
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



def parse_keyvals(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("[") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if not key.replace("_", "a").isalnum() or not (key[0].isalpha() or key[0] == "_"):
            continue
        out[key] = value.strip()
    return out



def infer_request_refs(request: PipelineJobRequest) -> dict[str, str]:
    parsed = _parse_cli_argv([str(x) for x in request.argv])
    refs: dict[str, str] = {}
    for key in ("pipeline_key", "data_version", "out_version", "run_id", "qc_run", "model_version", "scoring_run", "report_version", "pack_id"):
        value = str(parsed.get(key) or "").strip()
        if value:
            refs[key] = value
    if refs.get("out_version") and not refs.get("data_version"):
        refs["data_version"] = refs["out_version"]
    if not refs.get("run_id"):
        for key in ("pack_id", "report_version", "scoring_run", "model_version", "qc_run"):
            value = str(refs.get(key) or "").strip()
            if value:
                refs["run_id"] = value
                break
    for key in ("config", "cfg", "mapping", "rules"):
        value = str(parsed.get(key) or "").strip()
        if value:
            refs["config_version"] = value
            break
    return refs



def make_job_log_path(*, logs_dir: Path, kind: str) -> Path:
    return Path(logs_dir) / f"job_{_sanitize_job_kind(kind)}_{uuid4().hex}.log"



def build_ingest_job_request(*, dataset_key: str, file_path: Path, mapping_path: Path, data_version: str, artifacts_root: Path, contracts_dir: Path) -> PipelineJobRequest:
    ds = str(dataset_key).strip()
    return PipelineJobRequest(
        kind=f"ingest_{ds}",
        object_id=f"ingest_{ds}",
        argv=[
            'ingest', '--dataset', ds, '--file', str(file_path), '--mapping', str(mapping_path), '--out-version', str(data_version), '--artifacts', str(artifacts_root), '--contracts', str(contracts_dir),
        ],
        extra_after={'source_file': str(file_path), 'mapping_file': str(mapping_path)},
    )



def build_qc_job_request(*, data_version: str, artifacts_root: Path, contracts_dir: Path) -> PipelineJobRequest:
    return PipelineJobRequest(
        kind='qc',
        object_id='qc',
        argv=['qc', '--data-version', str(data_version), '--artifacts', str(artifacts_root), '--contracts', str(contracts_dir)],
    )



def build_train_job_request(*, data_version: str, qc_run: str, artifacts_root: Path, model_version: str | None = None, config_path: Path | None = None) -> PipelineJobRequest:
    argv = ['train', '--data-version', str(data_version), '--qc-run', str(qc_run), '--artifacts', str(artifacts_root)]
    if str(model_version or '').strip():
        argv.extend(['--model-version', str(model_version).strip()])
    if config_path is not None and str(config_path).strip():
        argv.extend(['--config', str(config_path)])
    return PipelineJobRequest(
        kind='train',
        object_id='train',
        argv=argv,
    )



def build_score_job_request(*, data_version: str, model_version: str, artifacts_root: Path, scoring_run: str | None = None, config_path: Path | None = None) -> PipelineJobRequest:
    argv = ['score', '--data-version', str(data_version), '--model-version', str(model_version), '--artifacts', str(artifacts_root)]
    if str(scoring_run or '').strip():
        argv.extend(['--scoring-run', str(scoring_run).strip()])
    if config_path is not None and str(config_path).strip():
        argv.extend(['--config', str(config_path)])
    return PipelineJobRequest(
        kind='score',
        object_id='score',
        argv=argv,
    )



def build_repro_job_request(*, data_version: str, asof_date: str, cfg_path: Path, artifacts_root: Path) -> PipelineJobRequest:
    return PipelineJobRequest(
        kind='repro',
        object_id='repro',
        argv=['repro', '--data-version', str(data_version), '--asof-date', str(asof_date), '--cfg', str(cfg_path), '--artifacts', str(artifacts_root)],
        extra_after={'asof_date': str(asof_date)},
    )



def build_report_job_request(*, data_version: str, qc_run: str, model_version: str, scoring_run: str, mode: str, artifacts_root: Path, llm_model: str | None = None) -> PipelineJobRequest:
    argv = ['report', '--data-version', str(data_version), '--qc-run', str(qc_run), '--model-version', str(model_version), '--scoring-run', str(scoring_run), '--mode', str(mode), '--artifacts', str(artifacts_root)]
    if str(llm_model or '').strip():
        argv.extend(['--llm-model', str(llm_model).strip()])
    return PipelineJobRequest(
        kind='report',
        object_id='report',
        argv=argv,
    )



def build_pack_job_request(*, data_version: str, qc_run: str, model_version: str, scoring_run: str, report_version: str, artifacts_root: Path, pack_id: str | None = None) -> PipelineJobRequest:
    argv = ['pack', '--data-version', str(data_version), '--qc-run', str(qc_run), '--model-version', str(model_version), '--scoring-run', str(scoring_run), '--report-version', str(report_version), '--artifacts', str(artifacts_root)]
    if str(pack_id or '').strip():
        argv.extend(['--pack-id', str(pack_id).strip()])
    return PipelineJobRequest(
        kind='pack',
        object_id='pack',
        argv=argv,
    )



def enqueue_pipeline_job(
    conn,
    *,
    request: PipelineJobRequest,
    tenant_id: str,
    user_id: int,
    username: str,
    logs_dir: Path,
    queue_name: str | None = None,
    retry_of_job_id: int | None = None,
    next_attempt_at: str | None = None,
    retry_source: str | None = None,
) -> int:
    job_id = int(create_job(
        conn,
        kind=request.kind,
        tenant_id=str(tenant_id),
        user_id=int(user_id),
        user=str(username),
        command=request.command,
        args={'argv': list(request.argv)},
        log_path=make_job_log_path(logs_dir=logs_dir, kind=request.kind),
        max_attempts=request.max_attempts,
        queue_name=queue_name,
        retry_of_job_id=retry_of_job_id,
        next_attempt_at=next_attempt_at,
        retry_source=retry_source,
    ))
    refs = infer_request_refs(request)
    log_event(
        'pipeline.job_enqueued',
        component='core.job_runner',
        job_id=job_id,
        user_id=user_id,
        tenant_id=tenant_id,
        command=request.argv[0] if request.argv else request.kind,
        **refs,
    )
    return job_id



def dispatch_pipeline_cli(argv: list[str]) -> int:
    from genomeai.cli import main

    return int(main(list(argv)))



def run_pipeline_job(request: PipelineJobRequest) -> int:
    return dispatch_pipeline_cli(request.argv)



def run_pipeline_job_logged(request: PipelineJobRequest, *, stream: TextIO, log_path: str | None = None) -> PipelineExecutionResult:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        exit_code = int(run_pipeline_job(request))
    text = buffer.getvalue()
    if text:
        stream.write(text)
        if not text.endswith("\n"):
            stream.write("\n")
        stream.flush()
    kv = parse_keyvals(text)
    return PipelineExecutionResult(
        request=request,
        exit_code=int(exit_code),
        log_path=str(log_path) if log_path else None,
        kv=kv,
    )



def can_execute_job_in_application(job: dict[str, Any]) -> bool:
    request = pipeline_request_from_job(job)
    if request is None:
        return False
    pipeline_key = str(request.argv[0] if request.argv else "").strip().lower()
    return pipeline_key in PIPELINE_JOB_KEYS



def pipeline_request_from_job(job: dict[str, Any]) -> PipelineJobRequest | None:
    try:
        args = json.loads(job.get("args_json") or "{}") if isinstance(job.get("args_json"), str) else dict(job.get("args_json") or {})
    except Exception:
        args = {}
    argv = [str(x) for x in (args.get("argv") or [])]
    if not argv:
        return None
    pipeline_key = str(argv[0]).strip().lower()
    if pipeline_key not in PIPELINE_JOB_KEYS:
        return None
    return PipelineJobRequest(
        kind=str(job.get("kind") or pipeline_key),
        object_id=str(job.get("kind") or pipeline_key),
        argv=argv,
        command=str(job.get("command") or "python -m genomeai"),
        extra_after={},
        max_attempts=int(job.get("max_attempts") or 0) or None,
    )



def run_pipeline_job_from_record(job: dict[str, Any], *, stream: TextIO, log_path: str | None = None) -> PipelineExecutionResult:
    request = pipeline_request_from_job(job)
    if request is None:
        raise ValueError(f"unsupported pipeline job record: kind={job.get('kind')!r}")
    return run_pipeline_job_logged(request, stream=stream, log_path=log_path)


@contextlib.contextmanager
def pipeline_job_environment(*, project_root: Path | None = None) -> Any:
    old_cwd = Path.cwd()
    env_old = os.environ.get("PYTHONPATH", "")
    try:
        if project_root is not None:
            repo_root = str(Path(project_root).resolve())
            src_root = str((Path(project_root).resolve() / "src"))
            parts = [repo_root, src_root] + ([env_old] if env_old else [])
            os.environ["PYTHONPATH"] = os.pathsep.join([p for p in parts if p])
            os.chdir(repo_root)
        yield
    finally:
        if project_root is not None:
            if env_old:
                os.environ["PYTHONPATH"] = env_old
            else:
                os.environ.pop("PYTHONPATH", None)
            os.chdir(old_cwd)


__all__ = [
    'PIPELINE_JOB_KEYS',
    'PipelineExecutionResult',
    'PipelineJobRequest',
    'build_ingest_job_request',
    'build_qc_job_request',
    'build_train_job_request',
    'build_score_job_request',
    'build_repro_job_request',
    'build_report_job_request',
    'build_pack_job_request',
    'enqueue_pipeline_job',
    'make_job_log_path',
    'dispatch_pipeline_cli',
    'run_pipeline_job',
    'run_pipeline_job_logged',
    'pipeline_request_from_job',
    'run_pipeline_job_from_record',
    'can_execute_job_in_application',
    'infer_request_refs',
    'parse_keyvals',
    'pipeline_job_environment',
]

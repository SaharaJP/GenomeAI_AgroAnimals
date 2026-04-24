from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional

from core.infra.web_db import (
    create_retry_job,
    fetch_next_queued_job,
    get_job,
    get_job_by_public_id,
    get_settings,
    mark_job_finished,
    mark_job_running,
)
from .jobs_v2 import discover_job_artifacts, is_auto_retry_allowed, load_job_runner_config
from .observability import record_job_finish, record_job_start
from core.audit.events import write_audit
from core.infra.queue_runtime import (
    QueueEnvelope,
    QueueRuntimeConfigError,
    resolve_queue_runtime_broker,
    resolve_queue_runtime_settings,
)

from core.observability import correlation_scope, ensure_request_id, get_structured_logger
from core.workflow import AlertCreate, create_alert
from core.application import (
    can_execute_job_in_application,
    pipeline_job_environment,
    run_pipeline_job_from_record,
)


KEYVAL_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)=(.*)$")
worker_logger = get_structured_logger("web.worker")



def parse_keyvals(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        m = KEYVAL_RE.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


class JobWorker:
    """Very small in-process queue worker.

    - Jobs are stored in postgres.
    - A single thread picks queued jobs and runs genomeai CLI via subprocess.
    - Stdout/stderr are appended to a per-job log file.

    This is intentionally minimal for B0 MVP.
    """

    def __init__(self, *, execution_model: str = "embedded", worker_id: str | None = None) -> None:
        self.settings = get_settings()
        self.cfg = load_job_runner_config(self.settings.project_root)
        self.execution_model = str(execution_model or "embedded").strip().lower() or "embedded"
        self.worker_id = str(worker_id or f"{self.execution_model}-worker-{os.getpid()}").strip()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _queue_backend(self) -> str:
        try:
            return str(resolve_queue_runtime_settings().backend or "postgres")
        except Exception:
            return "postgres"

    def _ensure_execution_model_allowed(self) -> None:
        settings = resolve_queue_runtime_settings()
        if settings.adult_mode and settings.backend == "redis" and self.execution_model != "dedicated":
            raise RuntimeError("adult contour forbids embedded worker; dedicated redis worker required")

    def start(self) -> None:
        self._ensure_execution_model_allowed()
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None

    def run_once(self) -> bool:
        self._ensure_execution_model_allowed()
        """Run a single queued job synchronously.

        Returns True if a job was processed, False if queue is empty.
        Useful for on-prem smoke tests and admin scripts.
        """
        conn = self._get_conn()
        try:
            if self._queue_backend() == "redis":
                broker = resolve_queue_runtime_broker()
                claimed = broker.claim(queue_name=self.cfg.queue_name_default, worker_id=self.worker_id)
                if not claimed:
                    return False
                job = get_job(conn, int(claimed.job_id)) or get_job_by_public_id(conn, claimed.public_job_id)
                if not job:
                    broker.fail(claimed, worker_id=self.worker_id, reason="job_record_missing", final_status="failed")
                    return False
                self._run_job(conn, job, claimed=claimed, broker=broker)
                return True
            job = fetch_next_queued_job(conn)
            if not job:
                return False
            self._run_job(conn, job)
            return True
        finally:
            conn.close()

    def run_until_empty(self, *, max_jobs: int = 1000) -> int:
        self._ensure_execution_model_allowed()
        """Run queued jobs until the queue is empty (or max_jobs reached)."""
        ran = 0
        while ran < max_jobs and self.run_once():
            ran += 1
        return ran

    def _get_conn(self):
        from core.infra.postgres_compat import connect_postgres_compat
        return connect_postgres_compat()

    def _loop(self) -> None:
        while not self._stop.is_set():
            conn = self._get_conn()
            try:
                if self._queue_backend() == "redis":
                    broker = resolve_queue_runtime_broker()
                    claimed = broker.claim(queue_name=self.cfg.queue_name_default, worker_id=self.worker_id)
                    if not claimed:
                        time.sleep(self.cfg.cancel_poll_interval_sec)
                        continue
                    job = get_job(conn, int(claimed.job_id)) or get_job_by_public_id(conn, claimed.public_job_id)
                    if not job:
                        broker.fail(claimed, worker_id=self.worker_id, reason="job_record_missing", final_status="failed")
                        time.sleep(self.cfg.cancel_poll_interval_sec)
                        continue
                    self._run_job(conn, job, claimed=claimed, broker=broker)
                    continue
                job = fetch_next_queued_job(conn)
                if not job:
                    time.sleep(self.cfg.cancel_poll_interval_sec)
                    continue
                self._run_job(conn, job)
            finally:
                conn.close()

    def _run_job(self, conn, job: dict[str, Any], *, claimed: QueueEnvelope | None = None, broker: Any | None = None) -> None:
        job_id = int(job["id"])
        if not mark_job_running(conn, job_id):
            if broker is not None and claimed is not None:
                broker.fail(claimed, worker_id=self.worker_id, reason="job_not_queued_or_already_running", final_status="failed")
            return

        if broker is not None and claimed is not None:
            try:
                broker.heartbeat(claimed, worker_id=self.worker_id)
            except Exception:
                pass

        kind = str(job.get("kind") or "job")
        correlation = {
            "request_id": ensure_request_id(str(job.get("request_id") or job.get("public_job_id") or ""), prefix="job"),
            "job_id": job_id,
            "public_job_id": job.get("public_job_id"),
            "data_version": job.get("data_version"),
            "run_id": job.get("run_id") or job.get("report_version") or job.get("scoring_run") or job.get("model_version") or job.get("qc_run"),
            "user_id": job.get("user_id"),
            "tenant_id": job.get("tenant_id"),
            "component": "web.worker",
            "command": kind,
        }
        record_job_start(kind)
        t0 = time.time()

        log_path = Path(job["log_path"]).resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        args = json.loads(job["args_json"]) if job.get("args_json") else {}
        cmd = [self._python(), "-m", "genomeai"] + args.get("argv", [])

        env = os.environ.copy()
        repo_root = str(self.settings.project_root)
        src_root = str((self.settings.project_root / "src").resolve())
        existing = env.get("PYTHONPATH", "")
        parts = [repo_root, src_root] + ([existing] if existing else [])
        env["PYTHONPATH"] = os.pathsep.join([p for p in parts if p])
        env["GENOMEAI_REQUEST_ID"] = str(correlation.get("request_id") or "")
        env["GENOMEAI_JOB_ID"] = str(job_id)
        env["GENOMEAI_PUBLIC_JOB_ID"] = str(job.get("public_job_id") or "")
        if correlation.get("data_version"):
            env["GENOMEAI_DATA_VERSION"] = str(correlation.get("data_version"))
        if correlation.get("run_id"):
            env["GENOMEAI_RUN_ID"] = str(correlation.get("run_id"))
        if correlation.get("user_id") not in (None, ""):
            env["GENOMEAI_USER_ID"] = str(correlation.get("user_id"))
        if correlation.get("tenant_id"):
            env["GENOMEAI_TENANT_ID"] = str(correlation.get("tenant_id"))

        with correlation_scope(**correlation):
            worker_logger.info("job.started", job_id=job_id, public_job_id=job.get("public_job_id"), kind=kind)
            with log_path.open("a", encoding="utf-8") as f:
                f.write(f"[job {job_id}] START cmd={' '.join(cmd)}\n")
                f.flush()
                try:
                    timeout = int(getattr(self.settings, "job_timeout_sec", 0) or 0)
                    final_status = "done"
                    error_text: str | None = None
                    exit_code: int | None = None

                    if can_execute_job_in_application(job):
                        current = get_job(conn, job_id) or {}
                        current_status = str(current.get("status") or "")
                        if current_status == "cancel_requested":
                            f.write(f"[job {job_id}] CANCEL requested before application start\n")
                            f.flush()
                            final_status = "cancelled"
                            error_text = str(current.get("error_text") or "Cancellation requested by user")
                            exit_code = 130
                        else:
                            with pipeline_job_environment(project_root=self.settings.project_root):
                                execution = run_pipeline_job_from_record(job, stream=f, log_path=str(log_path))
                            exit_code = int(execution.exit_code)
                    else:
                        proc = subprocess.Popen(
                            cmd,
                            cwd=str(self.settings.project_root),
                            stdout=f,
                            stderr=subprocess.STDOUT,
                            env=env,
                        )

                        deadline = (time.time() + timeout) if timeout > 0 else None

                        while True:
                            wait_timeout = float(self.cfg.cancel_poll_interval_sec)
                            if deadline is not None:
                                wait_timeout = max(0.2, min(wait_timeout, max(0.0, deadline - time.time())))
                            try:
                                exit_code = int(proc.wait(timeout=wait_timeout))
                                break
                            except subprocess.TimeoutExpired:
                                pass

                            current = get_job(conn, job_id) or {}
                            current_status = str(current.get("status") or "")
                            if current_status == "cancel_requested":
                                f.write(f"[job {job_id}] CANCEL requested -> terminate\n")
                                f.flush()
                                final_status = "cancelled"
                                error_text = str(current.get("error_text") or "Cancellation requested by user")
                                try:
                                    proc.terminate()
                                except Exception:
                                    pass
                                try:
                                    exit_code = int(proc.wait(timeout=int(self.cfg.cancel_grace_sec)))
                                except Exception:
                                    try:
                                        proc.kill()
                                    except Exception:
                                        pass
                                    exit_code = 130
                                break

                            if deadline is not None and time.time() >= deadline:
                                f.write(f"[job {job_id}] TIMEOUT after {timeout}s -> terminate\n")
                                f.flush()
                                final_status = "failed"
                                error_text = f"Timeout after {timeout}s"
                                try:
                                    proc.terminate()
                                except Exception:
                                    pass
                                try:
                                    proc.wait(timeout=int(self.cfg.cancel_grace_sec))
                                except Exception:
                                    try:
                                        proc.kill()
                                    except Exception:
                                        pass
                                exit_code = 124
                                break

                        if exit_code is None:
                            exit_code = int(proc.returncode or 0)

                    if exit_code is None:
                        exit_code = 0
                    if final_status == "done" and exit_code != 0:
                        final_status = "failed"
                        error_text = error_text or f"Process exited with code {exit_code}"

                    try:
                        log_text = log_path.read_text(encoding="utf-8")
                    except Exception:
                        log_text = ""
                    kv = parse_keyvals(log_text)
                    artifacts = discover_job_artifacts(job, kv=kv, project_root=self.settings.project_root, artifacts_root=self.settings.artifacts_root)
                    result = {"kv": kv, "artifacts": artifacts}

                    scheduled_retry_job_id = None
                    if is_auto_retry_allowed(cfg=self.cfg, job=job, exit_code=exit_code, final_status=final_status):
                        try:
                            scheduled_retry_job_id = create_retry_job(
                                conn,
                                job_id,
                                delay_sec=float(self.cfg.auto_retry_backoff_sec),
                                retry_source="auto",
                            )
                            result["auto_retry_job_id"] = scheduled_retry_job_id
                            result["auto_retry_backoff_sec"] = float(self.cfg.auto_retry_backoff_sec)
                            f.write(
                                f"[job {job_id}] AUTO_RETRY queued retry_job_id={scheduled_retry_job_id} backoff_sec={self.cfg.auto_retry_backoff_sec}\n"
                            )
                            f.flush()
                            write_audit(
                                conn,
                                tenant_id=str(job.get("tenant_id") or "default"),
                                user_id=int(job.get("user_id") or 0),
                                username=str(job.get("user") or "system"),
                                role="system",
                                action="pipeline.auto_retry_scheduled",
                                object_type="job",
                                object_id=str(scheduled_retry_job_id),
                                data_version=job.get("data_version"),
                                run_id=job.get("run_id") or job.get("report_version") or job.get("scoring_run") or job.get("qc_run"),
                                before={"job_id": job_id, "status": final_status, "exit_code": exit_code},
                                after={"retry_job_id": scheduled_retry_job_id, "backoff_sec": float(self.cfg.auto_retry_backoff_sec)},
                                status="OK",
                            )
                        except Exception as retry_exc:
                            result["auto_retry_error"] = str(retry_exc)
                            f.write(f"[job {job_id}] WARN auto_retry_schedule_failed: {type(retry_exc).__name__}: {retry_exc}\n")
                            f.flush()

                    mark_job_finished(
                        conn,
                        job_id,
                        status=final_status,
                        exit_code=exit_code,
                        result=result,
                        artifacts=artifacts,
                        error_text=error_text,
                    )
                    if broker is not None and claimed is not None:
                        try:
                            if final_status in ("done", "cancelled"):
                                broker.ack(claimed, worker_id=self.worker_id)
                            else:
                                broker.fail(claimed, worker_id=self.worker_id, reason=error_text or f"exit_code={exit_code}", final_status=final_status)
                        except Exception:
                            pass
                    f.write(f"[job {job_id}] END status={final_status} exit_code={exit_code}\n")
                    f.flush()

                    duration = max(0.0, time.time() - t0)
                    record_job_finish(kind, status=final_status, exit_code=exit_code, duration_sec=duration)
                    worker_logger.info(
                        "job.finished",
                        job_id=job_id,
                        public_job_id=job.get("public_job_id"),
                        kind=kind,
                        status=final_status,
                        exit_code=exit_code,
                        duration_sec=duration,
                    )

                    if final_status not in ("done", "cancelled") and scheduled_retry_job_id is None:
                        try:
                            tenant_id = str(job.get("tenant_id") or "default")
                            create_alert(
                                conn,
                                tenant_id=tenant_id,
                                a=AlertCreate(
                                    alert_type="ops.job_failed",
                                    title=f"Job failed: {kind}",
                                    source="web_cabinet.worker",
                                    cause=f"exit_code={exit_code}",
                                    confidence=1.0,
                                    object_type="job",
                                    object_id=str(job_id),
                                    deadline=None,
                                    owner_user_id=None,
                                    attachments=[{"type": "log", "path": str(log_path)}],
                                    why={"kind": kind, "job_id": job_id, "timeout_sec": int(self.settings.job_timeout_sec)},
                                    what_to_do=[
                                        {"step": "Откройте лог job и найдите первую ошибку", "log_path": str(log_path)},
                                        {"step": "Проверьте доступность artifacts/web storage и права на запись"},
                                        {"step": "Если ошибка повторяется — создайте задачу для инженера и приложите лог"},
                                    ],
                                    dedupe_key=f"ops.job_failed:{kind}:{exit_code}",
                                ),
                            )
                        except Exception:
                            f.write(f"[job {job_id}] WARN alert_create_failed\n")
                            f.flush()
                except Exception as e:
                    f.write(f"[job {job_id}] EXCEPTION: {type(e).__name__}: {e}\n")
                    f.flush()
                    mark_job_finished(conn, job_id, status="failed", exit_code=1, result={"error": str(e)}, error_text=str(e))
                    if broker is not None and claimed is not None:
                        try:
                            broker.fail(claimed, worker_id=self.worker_id, reason=str(e), final_status="failed")
                        except Exception:
                            pass

                    duration = max(0.0, time.time() - t0)
                    record_job_finish(kind, status="failed", exit_code=1, duration_sec=duration)
                    worker_logger.error(
                        "job.failed",
                        job_id=job_id,
                        public_job_id=job.get("public_job_id"),
                        kind=kind,
                        error=f"{type(e).__name__}: {e}",
                        duration_sec=duration,
                    )

    @staticmethod
    def _python() -> str:
        return os.environ.get("PYTHON", os.sys.executable)

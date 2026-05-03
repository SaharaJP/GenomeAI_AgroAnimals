from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _build_identity_mapping_upload(dataset_key: str, csv_path: Path) -> tuple[str, bytes, str]:
    header = csv_path.read_text(encoding="utf-8").splitlines()[0].split(",")
    lines = [f"dataset: {dataset_key}", "columns:"]
    lines.extend([f"  {name}: {name}" for name in header])
    payload = "\n".join(lines) + "\n"
    return (f"{dataset_key}_identity.yaml", payload.encode("utf-8"), "text/yaml")


def _login(client, username: str, password: str) -> None:
    r = client.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    if r.status_code not in (302, 303):
        raise RuntimeError(f"login failed for {username}: {r.status_code}")


def _logout(client) -> None:
    client.get("/logout", follow_redirects=False)


class _StepTimer:
    def __init__(self) -> None:
        self.timings: dict[str, float] = {}

    def run(self, key: str, fn):
        started = perf_counter()
        result = fn()
        self.timings[key] = max(0.0, perf_counter() - started)
        return result


def run_web_smoke_scenario(*, workdir: Path, data_version: str | None = None, clean: bool = False) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    if clean and workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    artifacts_root = workdir / "artifacts"
    web_storage = workdir / "web_storage"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    web_storage.mkdir(parents=True, exist_ok=True)

    os.environ["GENOMEAI_PROJECT_ROOT"] = str(repo_root)
    os.environ["GENOMEAI_ARTIFACTS_ROOT"] = str(artifacts_root)
    os.environ["GENOMEAI_WEB_STORAGE"] = str(web_storage)
    os.environ["GENOMEAI_WEB_DISABLE_WORKER"] = "1"

    from fastapi.testclient import TestClient  # noqa: WPS433

    importlib.invalidate_caches()
    db_module = importlib.import_module("web_cabinet.db")  # noqa: WPS433
    worker_module = importlib.import_module("web_cabinet.worker")  # noqa: WPS433
    importlib.reload(db_module)
    importlib.reload(worker_module)
    app_module = importlib.import_module("web_cabinet.app")  # noqa: WPS433
    app_module = importlib.reload(app_module)

    app = app_module.app
    connect = db_module.connect
    get_settings = db_module.get_settings
    list_jobs = db_module.list_jobs
    JobWorker = worker_module.JobWorker

    settings = get_settings()
    dv = data_version or f"dv_websmoke_{_ts()}"
    timer = _StepTimer()
    total_started = perf_counter()

    def run_jobs() -> None:
        worker = JobWorker()
        worker.run_until_empty(max_jobs=200)

    def last_kv(kind: str) -> dict[str, str]:
        conn = connect(settings.db_path)
        try:
            jobs = [j for j in list_jobs(conn, limit=500) if j["kind"] == kind]
            if not jobs:
                raise RuntimeError(f"no jobs of kind={kind}")
            j = jobs[0]
            if j["status"] != "done":
                raise RuntimeError(f"job kind={kind} not done: status={j['status']}")
            rj = json.loads(j["result_json"]) if j.get("result_json") else {}
            return dict(rj.get("kv") or {})
        finally:
            conn.close()

    base = repo_root / "data" / "examples"
    farms_path = base / "dm_farms.csv"
    animals_path = base / "dm_animals.csv"
    lact_path = base / "dm_lactations.csv"
    if not farms_path.exists() or not animals_path.exists() or not lact_path.exists():
        raise RuntimeError("example dm_* files not found under data/examples")

    farms_mapping_upload = _build_identity_mapping_upload("farms", farms_path)
    animals_mapping_upload = _build_identity_mapping_upload("animals", animals_path)
    lactations_mapping_upload = _build_identity_mapping_upload("lactations", lact_path)

    qc_run = ""
    model_version = ""
    scoring_run = ""
    report_version = ""
    pack_zip = ""

    try:
        with TestClient(app) as client:
            def rbac_step() -> None:
                _login(client, "viewer", "viewer")
                try:
                    r = client.post("/qc/run", data={"data_version": dv}, follow_redirects=False)
                    if r.status_code != 403:
                        raise RuntimeError(f"RBAC check failed: expected 403, got {r.status_code}")
                finally:
                    _logout(client)

            timer.run("rbac", rbac_step)

            _login(client, "operator", "operator")
            try:
                files = {
                    "farms_file": ("dm_farms.csv", farms_path.read_bytes(), "text/csv"),
                    "animals_file": ("dm_animals.csv", animals_path.read_bytes(), "text/csv"),
                    "lactations_file": ("dm_lactations.csv", lact_path.read_bytes(), "text/csv"),
                    "farms_mapping_upload": farms_mapping_upload,
                    "animals_mapping_upload": animals_mapping_upload,
                    "lactations_mapping_upload": lactations_mapping_upload,
                }
                data = {
                    "data_version": dv,
                    "farms_mapping_path": "configs/mappings/farms_example.yaml",
                    "animals_mapping_path": "configs/mappings/animals_example.yaml",
                    "lactations_mapping_path": "configs/mappings/lactations_example.yaml",
                }

                def ingest_all_step() -> None:
                    r = client.post("/upload/ingest-all", data=data, files=files, follow_redirects=False)
                    if r.status_code not in (302, 303):
                        raise RuntimeError(f"ingest-all failed: {r.status_code}")
                    run_jobs()
                    _ = last_kv("ingest_farms")
                    _ = last_kv("ingest_animals")
                    _ = last_kv("ingest_lactations")

                timer.run("ingest_all", ingest_all_step)

                def qc_step() -> str:
                    r = client.post("/qc/run", data={"data_version": dv}, follow_redirects=False)
                    if r.status_code not in (302, 303):
                        raise RuntimeError(f"qc enqueue failed: {r.status_code}")
                    run_jobs()
                    qc_kv = last_kv("qc")
                    value = qc_kv.get("qc_run") or ""
                    if not value:
                        raise RuntimeError("qc_run not found in job kv")
                    return value

                qc_run = timer.run("qc", qc_step)

                def train_step() -> str:
                    r = client.post("/train/run", data={"data_version": dv, "qc_run": qc_run}, follow_redirects=False)
                    if r.status_code not in (302, 303):
                        raise RuntimeError(f"train enqueue failed: {r.status_code}")
                    run_jobs()
                    tr_kv = last_kv("train")
                    value = tr_kv.get("model_version") or ""
                    if not value:
                        raise RuntimeError("model_version not found in job kv")
                    return value

                model_version = timer.run("train", train_step)

                def score_step() -> str:
                    r = client.post("/score/run", data={"data_version": dv, "model_version": model_version}, follow_redirects=False)
                    if r.status_code not in (302, 303):
                        raise RuntimeError(f"score enqueue failed: {r.status_code}")
                    run_jobs()
                    sc_kv = last_kv("score")
                    value = sc_kv.get("scoring_run") or ""
                    if not value:
                        raise RuntimeError("scoring_run not found in job kv")
                    return value

                scoring_run = timer.run("score", score_step)

                def report_step() -> str:
                    r = client.post(
                        "/reports/run",
                        data={
                            "data_version": dv,
                            "qc_run": qc_run,
                            "model_version": model_version,
                            "scoring_run": scoring_run,
                            "mode": "fallback",
                        },
                        follow_redirects=False,
                    )
                    if r.status_code not in (302, 303):
                        raise RuntimeError(f"report enqueue failed: {r.status_code}")
                    run_jobs()
                    rep_kv = last_kv("report")
                    value = rep_kv.get("report_version") or ""
                    if not value:
                        raise RuntimeError("report_version not found in job kv")
                    return value

                report_version = timer.run("report", report_step)

                def decisions_step() -> None:
                    r = client.post("/decisions/init", data={"data_version": dv, "scoring_run": scoring_run}, follow_redirects=False)
                    if r.status_code not in (302, 303):
                        raise RuntimeError(f"decision init enqueue failed: {r.status_code}")
                    run_jobs()

                    r = client.post(
                        "/decisions/add",
                        data={
                            "data_version": dv,
                            "animal_id": "A001",
                            "lactation_id": "A001__1",
                            "recommendation_type": "PRIORITY",
                            "decision": "ACCEPT",
                            "comment": "smoke",
                            "scoring_run": scoring_run,
                        },
                        follow_redirects=False,
                    )
                    if r.status_code not in (302, 303):
                        raise RuntimeError(f"decision add enqueue failed: {r.status_code}")
                    run_jobs()

                timer.run("decisions", decisions_step)

                def pack_step() -> str:
                    r = client.post(
                        "/pack/run",
                        data={
                            "data_version": dv,
                            "qc_run": qc_run,
                            "model_version": model_version,
                            "scoring_run": scoring_run,
                            "report_version": report_version,
                        },
                        follow_redirects=False,
                    )
                    if r.status_code not in (302, 303):
                        raise RuntimeError(f"pack enqueue failed: {r.status_code}")
                    run_jobs()
                    pk_kv = last_kv("pack")
                    value = pk_kv.get("pack_zip") or ""
                    if value and not Path(value).exists():
                        raise RuntimeError(f"pack_zip missing: {value}")
                    return value

                pack_zip = timer.run("pack", pack_step)
            finally:
                _logout(client)

        return {
            "ok": True,
            "workdir": str(workdir),
            "data_version": dv,
            "qc_run": qc_run,
            "model_version": model_version,
            "scoring_run": scoring_run,
            "report_version": report_version,
            "pack_zip": pack_zip,
            "timings": timer.timings,
            "duration_sec": max(0.0, perf_counter() - total_started),
        }
    except Exception as exc:
        return {
            "ok": False,
            "workdir": str(workdir),
            "data_version": dv,
            "timings": timer.timings,
            "duration_sec": max(0.0, perf_counter() - total_started),
            "reason": str(exc),
        }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m web_cabinet.smoke")
    p.add_argument(
        "--workdir",
        default=None,
        help="If set, store artifacts/web_storage under this dir (won't auto-delete).",
    )
    p.add_argument("--clean", action="store_true", help="If set, wipe --workdir before running.")
    p.add_argument("--data-version", default=None, help="Optional fixed data_version.")
    p.add_argument("--timing-json", default=None, help="Optional path to write machine-readable timing report.")
    args = p.parse_args(argv)

    temp_ctx = None
    if args.workdir:
        workdir = Path(args.workdir).resolve()
    else:
        temp_ctx = tempfile.TemporaryDirectory(prefix="genomeai_web_smoke_")
        workdir = Path(temp_ctx.name)

    try:
        result = run_web_smoke_scenario(workdir=workdir, data_version=args.data_version, clean=bool(args.clean))
        if getattr(args, "timing_json", None):
            timing_path = Path(args.timing_json).resolve()
            timing_path.parent.mkdir(parents=True, exist_ok=True)
            timing_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not result.get("ok"):
            print("WEB_SMOKE_FAILED")
            print(f"workdir={result.get('workdir')}")
            print(f"data_version={result.get('data_version')}")
            print(f"reason={result.get('reason')}")
            return 2
        print("WEB_SMOKE_OK")
        print(f"workdir={result['workdir']}")
        print(f"data_version={result['data_version']}")
        print(f"qc_run={result['qc_run']}")
        print(f"model_version={result['model_version']}")
        print(f"scoring_run={result['scoring_run']}")
        print(f"report_version={result['report_version']}")
        if result.get("pack_zip"):
            print(f"pack_zip={result['pack_zip']}")
        return 0
    finally:
        if temp_ctx is not None:
            temp_ctx.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())

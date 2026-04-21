from __future__ import annotations

import inspect
import json
import re
import shutil
from pathlib import Path

from core.application import (
    PipelineExecutionResult,
    build_ingest_job_request,
    build_pack_job_request,
    build_qc_job_request,
    build_report_job_request,
    build_repro_job_request,
    build_score_job_request,
    build_train_job_request,
    can_execute_job_in_application,
    enqueue_pipeline_job,
    pipeline_request_from_job,
    run_pipeline_job,
)
from streamlit_app.pipeline_jobs import build_streamlit_pack_job_request, run_streamlit_pack_job


def test_t15_05_pipeline_job_builders_preserve_legacy_cli_argv_shapes(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    contracts = tmp_path / "contracts"
    cfg = tmp_path / "repro.yaml"

    ingest = build_ingest_job_request(
        dataset_key="animals",
        file_path=tmp_path / "animals.xlsx",
        mapping_path=tmp_path / "animals_mapping.yaml",
        data_version="dv_1",
        artifacts_root=artifacts,
        contracts_dir=contracts,
    )
    assert ingest.kind == "ingest_animals"
    assert ingest.argv == [
        "ingest",
        "--dataset",
        "animals",
        "--file",
        str(tmp_path / "animals.xlsx"),
        "--mapping",
        str(tmp_path / "animals_mapping.yaml"),
        "--out-version",
        "dv_1",
        "--artifacts",
        str(artifacts),
        "--contracts",
        str(contracts),
    ]

    assert build_qc_job_request(data_version="dv_1", artifacts_root=artifacts, contracts_dir=contracts).argv == [
        "qc", "--data-version", "dv_1", "--artifacts", str(artifacts), "--contracts", str(contracts)
    ]
    assert build_train_job_request(data_version="dv_1", qc_run="qc_1", artifacts_root=artifacts).argv == [
        "train", "--data-version", "dv_1", "--qc-run", "qc_1", "--artifacts", str(artifacts)
    ]
    assert build_score_job_request(data_version="dv_1", model_version="mdl_1", artifacts_root=artifacts).argv == [
        "score", "--data-version", "dv_1", "--model-version", "mdl_1", "--artifacts", str(artifacts)
    ]
    assert build_repro_job_request(data_version="dv_1", asof_date="2026-03-14", cfg_path=cfg, artifacts_root=artifacts).argv == [
        "repro", "--data-version", "dv_1", "--asof-date", "2026-03-14", "--cfg", str(cfg), "--artifacts", str(artifacts)
    ]
    assert build_report_job_request(
        data_version="dv_1",
        qc_run="qc_1",
        model_version="mdl_1",
        scoring_run="scr_1",
        mode="fallback",
        artifacts_root=artifacts,
    ).argv == [
        "report", "--data-version", "dv_1", "--qc-run", "qc_1", "--model-version", "mdl_1", "--scoring-run", "scr_1", "--mode", "fallback", "--artifacts", str(artifacts)
    ]
    assert build_pack_job_request(
        data_version="dv_1",
        qc_run="qc_1",
        model_version="mdl_1",
        scoring_run="scr_1",
        report_version="rep_1",
        artifacts_root=artifacts,
        pack_id="pack_fixed",
    ).argv == [
        "pack", "--data-version", "dv_1", "--qc-run", "qc_1", "--model-version", "mdl_1", "--scoring-run", "scr_1", "--report-version", "rep_1", "--artifacts", str(artifacts), "--pack-id", "pack_fixed"
    ]


def test_t15_05_enqueue_pipeline_job_preserves_job_refs(tmp_path: Path) -> None:
    from web_cabinet.db import connect, init_db

    storage = tmp_path / "web_storage"
    storage.mkdir(parents=True, exist_ok=True)
    db_path = storage / "web.db"
    conn = connect(db_path)
    init_db(conn)
    try:
        request = build_report_job_request(
            data_version="dv_1",
            qc_run="qc_1",
            model_version="mdl_1",
            scoring_run="scr_1",
            mode="fallback",
            artifacts_root=tmp_path / "artifacts",
        )
        job_id = enqueue_pipeline_job(
            conn,
            request=request,
            tenant_id="default",
            user_id=1,
            username="operator",
            logs_dir=storage / "logs",
        )
        row = conn.execute(
            "SELECT kind, pipeline_key, data_version, qc_run, model_version, scoring_run, report_version, run_id, command, args_json FROM jobs WHERE id=?",
            (job_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row[0] == "report"
    assert row[1] == "report"
    assert row[2] == "dv_1"
    assert row[3] == "qc_1"
    assert row[4] == "mdl_1"
    assert row[5] == "scr_1"
    assert row[6] is None
    assert row[7] == "scr_1"
    assert row[8] == "python -m genomeai"
    assert '"report"' in str(row[9])


def test_t15_05_run_pipeline_job_delegates_to_cli(monkeypatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    def fake_main(argv: list[str]) -> int:
        seen["argv"] = list(argv)
        return 7

    import genomeai.cli as cli_mod

    monkeypatch.setattr(cli_mod, "main", fake_main)
    request = build_qc_job_request(
        data_version="dv_1",
        artifacts_root=tmp_path / "artifacts",
        contracts_dir=tmp_path / "contracts",
    )
    rc = run_pipeline_job(request)
    assert rc == 7
    assert seen["argv"] == request.argv


def test_t15_05_pipeline_request_from_job_and_capability() -> None:
    job = {
        "kind": "pack",
        "command": "python -m genomeai",
        "args_json": json.dumps(
            {
                "argv": [
                    "pack",
                    "--data-version",
                    "dv_1",
                    "--qc-run",
                    "qc_1",
                    "--model-version",
                    "mdl_1",
                    "--scoring-run",
                    "scr_1",
                    "--report-version",
                    "rep_1",
                    "--artifacts",
                    "/tmp/artifacts",
                    "--pack-id",
                    "pack_fixed",
                ]
            }
        ),
    }
    request = pipeline_request_from_job(job)
    assert request is not None
    assert request.kind == "pack"
    assert request.argv[-2:] == ["--pack-id", "pack_fixed"]
    assert can_execute_job_in_application(job) is True
    assert can_execute_job_in_application({"kind": "sleep", "args_json": json.dumps({"argv": ["sleep", "--seconds", "1"]})}) is False



def _prepare_pack_inputs(root: Path, *, data_version: str, qc_run: str, model_version: str, scoring_run: str, report_version: str) -> None:
    base = root / data_version
    (base / "canonical").mkdir(parents=True, exist_ok=True)
    (base / "qc" / qc_run).mkdir(parents=True, exist_ok=True)
    (base / "models" / model_version).mkdir(parents=True, exist_ok=True)
    (base / "scoring" / scoring_run).mkdir(parents=True, exist_ok=True)
    (base / "reports" / report_version / "exports").mkdir(parents=True, exist_ok=True)
    (base / "metadata").mkdir(parents=True, exist_ok=True)

    (base / "canonical" / "animals.csv").write_text("animal_id,farm_id\nA001,F001\n", encoding="utf-8")
    (base / "qc" / qc_run / "qc_summary.json").write_text('{"qc_status":"OK"}\n', encoding="utf-8")
    (base / "models" / model_version / "model_metrics.json").write_text('{"mae":1.2}\n', encoding="utf-8")
    (base / "scoring" / scoring_run / "scored_latest.csv").write_text(
        "animal_id,lactation_no,action,farm_id\nA001,1,PRIORITY,F001\n",
        encoding="utf-8",
    )
    (base / "reports" / report_version / "report_summary.json").write_text(
        json.dumps({"data_version": data_version, "report_version": report_version}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (base / "reports" / report_version / "exports" / "report.html").write_text("<html><body>ok</body></html>", encoding="utf-8")
    (base / "metadata" / "manifest.json").write_text('{"schema":"manifest"}\n', encoding="utf-8")



def _load_pack_outputs(root: Path, *, data_version: str, pack_id: str) -> tuple[dict[str, object], dict[str, object]]:
    pack_dir = root / data_version / "pilot_packs" / pack_id
    versions = json.loads((pack_dir / "versions.json").read_text(encoding="utf-8"))
    manifest = json.loads((pack_dir / "pack_manifest.json").read_text(encoding="utf-8"))
    return versions, manifest



def test_t15_05_cli_vs_miniweb_vs_streamlit_pack_outputs_match(tmp_path: Path) -> None:
    import genomeai.cli as cli_mod

    dv = "dv_same"
    qc_run = "qc_same"
    model_version = "mdl_same"
    scoring_run = "scr_same"
    report_version = "rep_same"
    pack_id = "pack_same"

    cli_root = tmp_path / "cli_artifacts"
    web_root = tmp_path / "web_artifacts"
    streamlit_root = tmp_path / "streamlit_artifacts"
    for root in (cli_root, web_root, streamlit_root):
        _prepare_pack_inputs(root, data_version=dv, qc_run=qc_run, model_version=model_version, scoring_run=scoring_run, report_version=report_version)

    cli_rc = cli_mod.main([
        "pack",
        "--data-version",
        dv,
        "--qc-run",
        qc_run,
        "--model-version",
        model_version,
        "--scoring-run",
        scoring_run,
        "--report-version",
        report_version,
        "--artifacts",
        str(cli_root),
        "--pack-id",
        pack_id,
    ])
    assert cli_rc == 0

    web_request = build_pack_job_request(
        data_version=dv,
        qc_run=qc_run,
        model_version=model_version,
        scoring_run=scoring_run,
        report_version=report_version,
        artifacts_root=web_root,
        pack_id=pack_id,
    )
    assert run_pipeline_job(web_request) == 0

    streamlit_result = run_streamlit_pack_job(
        data_version=dv,
        qc_run=qc_run,
        model_version=model_version,
        scoring_run=scoring_run,
        report_version=report_version,
        artifacts_root=streamlit_root,
        pack_id=pack_id,
        log_path=tmp_path / "streamlit_pack.log",
    )
    assert streamlit_result.exit_code == 0
    assert streamlit_result.kv.get("pack_id") == pack_id

    cli_versions, cli_manifest = _load_pack_outputs(cli_root, data_version=dv, pack_id=pack_id)
    web_versions, web_manifest = _load_pack_outputs(web_root, data_version=dv, pack_id=pack_id)
    streamlit_versions, streamlit_manifest = _load_pack_outputs(streamlit_root, data_version=dv, pack_id=pack_id)

    def normalize_versions(payload: dict[str, object]) -> dict[str, object]:
        out = dict(payload)
        decision_log = str(out.get("decision_log") or "")
        if decision_log:
            out["decision_log"] = str(Path(decision_log).name)
        return out

    assert normalize_versions(cli_versions) == normalize_versions(web_versions) == normalize_versions(streamlit_versions)

    def normalize_manifest(payload: dict[str, object]) -> dict[str, object]:
        return {k: v for k, v in payload.items() if str(k) != "versions.json"}

    assert normalize_manifest(cli_manifest) == normalize_manifest(web_manifest) == normalize_manifest(streamlit_manifest)



def test_t15_05_worker_uses_application_runner_for_pipeline_jobs(monkeypatch, tmp_path: Path) -> None:
    from web_cabinet.db import connect, create_job, get_job, init_db
    from web_cabinet.worker import JobWorker

    storage = tmp_path / "web_storage"
    artifacts = tmp_path / "artifacts"
    storage.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)

    import os

    os.environ["GENOMEAI_WEB_STORAGE"] = str(storage)
    os.environ["GENOMEAI_ARTIFACTS_ROOT"] = str(artifacts)
    os.environ["GENOMEAI_PROJECT_ROOT"] = str(Path.cwd())

    db_path = storage / "web.db"
    conn = connect(db_path)
    init_db(conn)
    job_id = create_job(
        conn,
        kind="qc",
        tenant_id="default",
        user_id=1,
        user="operator",
        command="python -m genomeai",
        args={"argv": ["qc", "--data-version", "dv_1", "--artifacts", str(artifacts), "--contracts", str(tmp_path / 'contracts')]},
        log_path=storage / "logs" / "job_qc.log",
    )
    conn.close()

    calls: list[dict[str, object]] = []

    def fake_run(job: dict[str, object], *, stream, log_path: str | None = None) -> PipelineExecutionResult:
        stream.write("data_version=dv_1\nqc_run=qc_1\n")
        stream.flush()
        calls.append({"kind": job.get("kind"), "log_path": log_path})
        req = pipeline_request_from_job(job)
        assert req is not None
        return PipelineExecutionResult(request=req, exit_code=0, log_path=log_path, kv={"data_version": "dv_1", "qc_run": "qc_1"})

    import web_cabinet.worker as worker_mod

    monkeypatch.setattr(worker_mod, "run_pipeline_job_from_record", fake_run)
    worker = JobWorker()
    assert worker.run_once() is True

    conn = connect(db_path)
    try:
        row = get_job(conn, job_id)
    finally:
        conn.close()
    assert row is not None
    assert row["status"] == "done"
    assert calls and calls[0]["kind"] == "qc"
    assert json.loads(row["result_json"])["kv"]["qc_run"] == "qc_1"



def test_t15_05_web_pipeline_routes_use_core_application_enqueue() -> None:
    app_path = Path("web_cabinet/app.py")
    text = app_path.read_text(encoding="utf-8")
    assert "from core.application import (" in text
    assert text.count("enqueue_pipeline_job(") >= 7

    for fn_name in ("ingest_all", "qc_run", "train_run", "score_run", "repro_run", "reports_run", "pack_run"):
        match = re.search(rf"def {fn_name}\(.*?\n(?=@app\.|def |$)", text, flags=re.S)
        assert match, fn_name
        block = match.group(0)
        assert "enqueue_pipeline_job(" in block, fn_name
        assert "create_job(" not in block, fn_name



def test_t15_05_job_runner_module_and_legacy_shim_are_importable() -> None:
    import core.application.job_runner as job_runner_mod
    import genomeai.application.job_runner as legacy_job_runner_mod

    source = inspect.getsource(job_runner_mod)
    assert "PipelineJobRequest" in source
    assert "run_pipeline_job_logged" in source
    assert legacy_job_runner_mod.build_qc_job_request is job_runner_mod.build_qc_job_request

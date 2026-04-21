from __future__ import annotations

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from streamlit_app.qc_workspace import build_qc_workspace_bundle, qc_next_step_actions


REPO_ROOT = Path(__file__).resolve().parents[1]


def _ctx(tmp_path: Path):
    web_storage_dir = tmp_path / "web_storage"
    artifacts_dir = tmp_path / "artifacts"
    web_storage_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(web_storage_dir=web_storage_dir, artifacts_dir=artifacts_dir)


def _seed_qc_run(base_dir: Path, *, data_version: str, qc_run: str) -> Path:
    qc_dir = base_dir / data_version / "qc" / qc_run
    qc_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema": "genomeai.qc_summary.v2",
        "data_version": data_version,
        "qc_run": qc_run,
        "qc_status": "ERROR",
        "datasets_loaded": {"dm_animals": 10, "dm_lactations": 12},
        "outputs": {
            "qc_report_xlsx": str((qc_dir / "qc_report.xlsx").resolve()),
            "qc_issues_csv": str((qc_dir / "qc_issues.csv").resolve()),
            "bad_rows_csv": str((qc_dir / "bad_rows.csv").resolve()),
            "qc_summary_json": str((qc_dir / "qc_summary.json").resolve()),
            "manifest_json": str((qc_dir / "manifest.json").resolve()),
        },
    }
    (qc_dir / "qc_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame(
        [
            {
                "qc_run": qc_run,
                "data_version": data_version,
                "rule_id": "core_animals_pk_unique",
                "domain": "core",
                "dataset": "dm_animals",
                "severity": "BLOCKER",
                "message": "",
                "remediation": "",
                "row_id": "dm_animals:12",
                "field": "animal_id",
                "sample_value": "A-001",
                "check": "pk_unique",
            },
            {
                "qc_run": qc_run,
                "data_version": data_version,
                "rule_id": "connectivity",
                "domain": "cross",
                "dataset": "dm_animals",
                "severity": "WARN",
                "message": "animal has no lactations",
                "remediation": "",
                "row_id": "dm_animals:33",
                "field": "animal_id",
                "sample_value": "A-099",
                "check": "connectivity",
            },
        ]
    ).to_csv(qc_dir / "qc_issues.csv", index=False)
    pd.DataFrame(
        [
            {"row_id": "dm_animals:12", "reason": "BLOCKER: pk_unique: duplicate animal_id"},
            {"row_id": "dm_animals:33", "reason": "WARN: connectivity: animal has no lactations"},
        ]
    ).to_csv(qc_dir / "bad_rows.csv", index=False)
    (qc_dir / "qc_report.xlsx").write_bytes(b"xlsx-bytes")
    (qc_dir / "manifest.json").write_text(json.dumps({"type": "qc"}, ensure_ascii=False), encoding="utf-8")
    return qc_dir


def test_t19_04_workspace_derives_counts_and_catalog_remediation(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    _seed_qc_run(ctx.artifacts_dir, data_version="dv_qc_ws", qc_run="qc_demo")

    bundle = build_qc_workspace_bundle(ctx, data_version="dv_qc_ws", qc_run="qc_demo")
    assert bundle["ok"] is True
    assert bundle["issue_counts"]["BLOCKER"] == 1
    assert bundle["issue_counts"]["WARN"] == 1
    assert not bundle["checks_tree"].empty

    rule_row = bundle["checks_tree"].loc[bundle["checks_tree"]["rule_id"] == "core_animals_pk_unique"].iloc[0].to_dict()
    assert "идентификаторы" in str(rule_row["remediation"]).lower() or "дубликат" in str(rule_row["message"]).lower()

    grid_row = bundle["issue_grid"].loc[bundle["issue_grid"]["rule_id"] == "core_animals_pk_unique"].iloc[0].to_dict()
    assert grid_row["next_step_effect"] == "blocks Train/Score/Report"


def test_t19_04_next_step_actions_blocker_vs_warn() -> None:
    blocked = qc_next_step_actions("ERROR", {"BLOCKER": 2, "WARN": 1})
    warned = qc_next_step_actions("WARN", {"WARN": 2, "INFO": 1})
    ready = qc_next_step_actions("PASS", {})

    assert blocked[0]["status"] == "Blocked"
    assert warned[0]["status"] == "Allowed with caution"
    assert ready[0]["status"] == "Ready"


def test_t19_04_bundle_zip_contains_report_and_summary(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    _seed_qc_run(ctx.artifacts_dir, data_version="dv_qc_zip", qc_run="qc_zip")
    bundle = build_qc_workspace_bundle(ctx, data_version="dv_qc_zip", qc_run="qc_zip")

    zip_path = tmp_path / "bundle.zip"
    zip_path.write_bytes(bundle["bundle_zip_bytes"])
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = sorted(zf.namelist())
    assert "qc_report.xlsx" in names
    assert "qc_summary.json" in names
    assert "qc_issues.csv" in names


def test_t19_04_docs_gate_and_page_reference_qc_workspace() -> None:
    doc = Path("docs/streamlit_qc_workspace.md").read_text(encoding="utf-8")
    gate = Path("ci/pytest_gate.txt").read_text(encoding="utf-8")
    page = Path("streamlit_app/pages/27_QC_Operations.py").read_text(encoding="utf-8")
    assumptions = Path("docs/assumptions.md").read_text(encoding="utf-8")

    assert "checks tree" in doc.lower()
    assert "blocker / warn / info" in doc.lower()
    assert "tests/test_t19_04_qc_workspace.py" in gate
    assert "Скачать QC bundle (.zip)" in page
    assert "T19-04" in assumptions

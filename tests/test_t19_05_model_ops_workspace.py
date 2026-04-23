from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from streamlit_app.model_ops_workspace import (
    build_model_compare_rows,
    build_model_ops_workspace_bundle,
    build_report_compare_rows,
    build_scoring_compare_rows,
)


def _ctx(tmp_path: Path):
    web_storage_dir = tmp_path / "web_storage"
    artifacts_dir = tmp_path / "artifacts"
    web_storage_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(web_storage_dir=web_storage_dir, artifacts_dir=artifacts_dir)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _seed_workspace_versions(base_dir: Path, *, data_version: str) -> None:
    dv_dir = base_dir / data_version
    canonical = dv_dir / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)
    for name in ("dm_farms.csv", "dm_animals.csv", "dm_lactations.csv"):
        (canonical / name).write_text("id\n1\n", encoding="utf-8")

    _write_json(
        dv_dir / "qc" / "qc_pass" / "qc_summary.json",
        {
            "schema": "genomeai.qc_summary.v2",
            "data_version": data_version,
            "qc_run": "qc_pass",
            "qc_status": "PASS",
            "issue_counts": {"INFO": 1},
            "outputs": {},
        },
    )
    _write_json(
        dv_dir / "qc" / "qc_warn" / "qc_summary.json",
        {
            "schema": "genomeai.qc_summary.v2",
            "data_version": data_version,
            "qc_run": "qc_warn",
            "qc_status": "WARN",
            "issue_counts": {"WARN": 2},
            "outputs": {},
        },
    )

    _write_json(
        dv_dir / "metadata" / "model_manifest.json",
        {
            "latest": "model_v2",
            "models": {
                "model_v1": {"created_at_utc": "2026-03-28T08:00:00+00:00", "config_version": "ml_v1", "seed": 7},
                "model_v2": {"created_at_utc": "2026-03-29T08:00:00+00:00", "config_version": "ml_v2", "seed": 42},
            },
        },
    )
    for model_version, qc_run, mae, rmse in (("model_v1", "qc_warn", 420.0, 510.0), ("model_v2", "qc_pass", 350.0, 470.0)):
        model_dir = dv_dir / "runs" / model_version / "model"
        _write_json(
            model_dir / "model_card.json",
            {
                "schema": "genomeai.model_card.v1",
                "created_at_utc": f"2026-03-29T08:00:0{1 if model_version == 'model_v1' else 2}+00:00",
                "data_version": data_version,
                "qc_run": qc_run,
                "model_version": model_version,
                "config_version": f"cfg_{model_version}",
                "seed": 42,
                "target": "milk_305d_kg",
                "metrics": {"mae": mae, "rmse": rmse},
            },
        )
        _write_json(
            model_dir / "train_summary.json",
            {
                "schema": "genomeai.train_summary.v1",
                "created_at_utc": f"2026-03-29T08:00:0{1 if model_version == 'model_v1' else 2}+00:00",
                "data_version": data_version,
                "qc_run": qc_run,
                "model_version": model_version,
                "config_version": f"cfg_{model_version}",
                "seed": 42,
                "target": "milk_305d_kg",
                "metrics": {"mae": mae, "rmse": rmse},
                "outputs": {},
            },
        )
        (model_dir / "model_card.md").write_text(f"# {model_version}\n", encoding="utf-8")

    _write_json(
        dv_dir / "metadata" / "scoring_manifest.json",
        {
            "latest": "score_v2",
            "scoring_runs": {
                "score_v1": {"created_at_utc": "2026-03-28T09:00:00+00:00", "model_version": "model_v1", "status": "ok"},
                "score_v2": {"created_at_utc": "2026-03-29T09:00:00+00:00", "model_version": "model_v2", "status": "ok"},
            },
        },
    )
    for scoring_run, model_version, n_scored in (("score_v1", "model_v1", 12), ("score_v2", "model_v2", 18)):
        scoring_dir = dv_dir / "runs" / scoring_run / "scoring"
        exports = scoring_dir / "exports"
        exports.mkdir(parents=True, exist_ok=True)
        _write_json(
            scoring_dir / "scoring_summary.json",
            {
                "schema": "genomeai.scoring_summary.v1",
                "created_at_utc": f"2026-03-29T09:00:0{1 if scoring_run == 'score_v1' else 2}+00:00",
                "data_version": data_version,
                "model_version": model_version,
                "scoring_run": scoring_run,
                "config_version": f"cfg_{model_version}",
                "status": "ok",
                "row_counts": {"scored": n_scored, "excluded": 1},
                "outputs": {
                    "animal_ranking_xlsx": str((exports / "animal_ranking.xlsx").resolve()),
                    "group_summary_xlsx": str((exports / "group_summary.xlsx").resolve()),
                    "recommendations_xlsx": str((exports / "recommendations.xlsx").resolve()),
                    "scored_latest_csv": str((scoring_dir / "scored_latest.csv").resolve()),
                    "explanations_csv": str((scoring_dir / "productivity_explanations.csv").resolve()),
                },
            },
        )
        for path in (exports / "animal_ranking.xlsx", exports / "group_summary.xlsx", exports / "recommendations.xlsx"):
            path.write_bytes(b"xlsx")
        (scoring_dir / "scored_latest.csv").write_text("animal_id,pred\nA1,1\n", encoding="utf-8")
        (scoring_dir / "productivity_explanations.csv").write_text("animal_id,reason\nA1,test\n", encoding="utf-8")

    _write_json(dv_dir / "metadata" / "report_manifest.json", {"latest": "report_v2", "reports": {}})
    for report_version, qc_run, model_version, scoring_run, mode_requested, llm_used in (
        ("report_v1", "qc_warn", "model_v1", "score_v1", "fallback", False),
        ("report_v2", "qc_pass", "model_v2", "score_v2", "llm", True),
    ):
        report_dir = dv_dir / "reports" / report_version
        exports = report_dir / "exports"
        exports.mkdir(parents=True, exist_ok=True)
        _write_json(
            report_dir / "report_summary.json",
            {
                "schema": "genomeai.report_summary.v1",
                "created_at_utc": f"2026-03-29T10:00:0{1 if report_version == 'report_v1' else 2}+00:00",
                "data_version": data_version,
                "qc_run": qc_run,
                "model_version": model_version,
                "scoring_run": scoring_run,
                "report_version": report_version,
                "mode_requested": mode_requested,
                "llm_used": llm_used,
                "inputs": {"fact_pack": str((report_dir / "fact_pack.json").resolve())},
                "outputs": {
                    "report_docx": str((exports / "report.docx").resolve()),
                    "report_pdf": str((exports / "report.pdf").resolve()),
                },
            },
        )
        (report_dir / "fact_pack.json").write_text("{}", encoding="utf-8")
        (exports / "report.docx").write_bytes(b"docx")
        (exports / "report.pdf").write_bytes(b"pdf")


def test_t19_05_workspace_bundle_shows_active_versions_and_lineage(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    _seed_workspace_versions(ctx.artifacts_dir, data_version="dv_model_ops")

    bundle = build_model_ops_workspace_bundle(
        ctx,
        data_version="dv_model_ops",
        qc_run="qc_pass",
        model_version="model_v2",
        scoring_run="score_v2",
        report_version="report_v2",
    )

    assert bundle["ok"] is True
    assert bundle["active_versions"]["data_version"] == "dv_model_ops"
    assert bundle["active_versions"]["model_version"] == "model_v2"
    assert any(row["status"] == "ready" for row in bundle["workflow_steps"] if row["step"] == "Report")
    lineage_map = {row["link"]: row for row in bundle["lineage_rows"]}
    assert lineage_map["model_version → qc_run"]["status"] == "ready"
    assert lineage_map["scoring_run → model_version"]["status"] == "ready"


def test_t19_05_workspace_detects_lineage_mismatch_and_compare_deltas(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    _seed_workspace_versions(ctx.artifacts_dir, data_version="dv_model_ops")

    bundle = build_model_ops_workspace_bundle(
        ctx,
        data_version="dv_model_ops",
        qc_run="qc_warn",
        model_version="model_v2",
        scoring_run="score_v1",
        report_version="report_v2",
    )

    report_step = next(row for row in bundle["workflow_steps"] if row["step"] == "Report")
    assert report_step["status"] == "caution"
    assert "Lineage требует review" in report_step["detail"]

    model_rows = build_model_compare_rows(bundle=bundle, current_id="model_v2", compare_id="model_v1")
    mae_row = next(row for row in model_rows if row["field"] == "mae")
    assert mae_row["trend"] == "improved"
    assert mae_row["delta"].startswith("-")

    score_rows = build_scoring_compare_rows(bundle=bundle, current_id="score_v2", compare_id="score_v1")
    scored_row = next(row for row in score_rows if row["field"] == "row_counts.scored")
    assert scored_row["delta"].startswith("+")

    report_rows = build_report_compare_rows(bundle=bundle, current_id="report_v2", compare_id="report_v1")
    mode_row = next(row for row in report_rows if row["field"] == "mode_requested")
    assert mode_row["trend"] == "changed"


def test_t19_05_docs_gate_and_pages_reference_workspace() -> None:
    doc = Path("docs/streamlit_model_ops_ux.md").read_text(encoding="utf-8")
    gate = Path("ci/pytest_gate.txt").read_text(encoding="utf-8")
    page_train = Path("streamlit_app/pages/28_Train_Operations.py").read_text(encoding="utf-8")
    page_score = Path("streamlit_app/pages/29_Score_Operations.py").read_text(encoding="utf-8")
    page_report = Path("streamlit_app/pages/30_Report_Operations.py").read_text(encoding="utf-8")
    assumptions = Path("docs/assumptions.md").read_text(encoding="utf-8")

    assert "train → score → report" in doc.lower()
    assert "fallback path" in doc.lower()
    assert "tests/test_t19_05_model_ops_workspace.py" in gate
    assert "render_model_ops_workspace" in page_train
    assert "render_model_ops_workspace" in page_score
    assert "render_model_ops_workspace" in page_report
    assert "T19-05" in assumptions

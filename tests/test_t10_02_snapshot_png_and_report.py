from __future__ import annotations

from datetime import datetime
from pathlib import Path

from genomeai.kpi_v2 import run_kpi
from genomeai.dashboard_director import DirectorSummaryInputs, export_director_summary
from genomeai.dashboard_reports import save_dashboard_snapshot_as_report


def test_t10_02_snapshot_png_and_save_as_report(tmp_path: Path):
    artifacts = tmp_path / "artifacts"
    dv = "dv_test_t10_02_snap"

    # KPI run
    run_kpi(
        data_version=dv,
        asof_date="2025-01-05",
        input_dir=Path("data/fixtures/target_v2"),
        artifacts_root=artifacts,
        config_kpi=Path("configs/kpi/kpi_v2.yaml"),
        config_thresholds=Path("configs/kpi/kpi_thresholds_v2.yaml"),
        run_id="kpi_test",
    )

    # Dashboard export (must create PNG)
    inputs = DirectorSummaryInputs(
        data_version=dv,
        artifacts_dir=artifacts,
        input_dir=Path("data/fixtures/target_v2"),
        kpi_run_id="kpi_test",
        asof_date=datetime.strptime("2025-01-05", "%Y-%m-%d").date(),
    )
    run_root = export_director_summary(inputs=inputs, run_id="dash_test")
    out_dir = run_root / "dashboards" / "director_summary"
    assert (out_dir / "director_summary.xlsx").exists()
    # PDF snapshot is required by T10-02 acceptance (export snapshot PDF/PNG)
    assert (out_dir / "director_summary.pdf").exists(), "PDF snapshot is required for T10-02"
    assert (out_dir / "director_summary.png").exists(), "PNG snapshot is required for T10-02"

    # Save snapshot as report_version
    res = save_dashboard_snapshot_as_report(
        artifacts_root=artifacts,
        data_version=dv,
        dashboard_run_id="dash_test",
        dashboard_kind="director_summary",
        report_version="reportdash_test",
        notes="unit test",
    )
    assert res.get("ok") is True
    rep_dir = Path(res["report_dir"])
    exports_dir = Path(res["exports_dir"])
    assert rep_dir.exists()
    assert exports_dir.exists()
    assert (exports_dir / "director_summary.png").exists()
    # Target run layout should be materialized
    run_root2 = artifacts / dv / "runs" / "reportdash_test"
    assert (run_root2 / "run_manifest.json").exists()
    assert (run_root2 / "checksums.json").exists()

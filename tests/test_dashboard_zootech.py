from __future__ import annotations

from pathlib import Path

import pandas as pd

from genomeai.dashboard_zootech import compute_group_analytics, export_zootech_dashboard, ZootechDashboardInputs


def _make_scored() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "farm_id": "F1",
                "animal_id": "A1",
                "lactation_no": 2,
                "calving_year": 2025,
                "calving_season": "winter",
                "parity": 2,
                "y_pred": 9000,
                "residual": 600,
                "confidence": "HIGH",
                "action": "PRIORITY",
            },
            {
                "farm_id": "F1",
                "animal_id": "A2",
                "lactation_no": 3,
                "calving_year": 2025,
                "calving_season": "winter",
                "parity": 3,
                "y_pred": 8200,
                "residual": -900,
                "confidence": "MEDIUM",
                "action": "CULL_CANDIDATE",
            },
        ]
    )


def test_compute_group_analytics_basic() -> None:
    scored = _make_scored()
    res = compute_group_analytics(scored)
    assert "group_stats" in res
    assert len(res["outliers"]) == 2


def test_export_zootech_dashboard(tmp_path: Path) -> None:
    # Build minimal artifacts layout with a scoring run
    dv = "dv_test"
    sr = "score_test"
    scoring_dir = tmp_path / dv / "runs" / sr / "scoring"
    scoring_dir.mkdir(parents=True, exist_ok=True)
    scored = _make_scored()
    scored.to_csv(scoring_dir / "scored_latest.csv", index=False, encoding="utf-8")
    pd.DataFrame().to_csv(scoring_dir / "group_summary.csv", index=False, encoding="utf-8")

    run_root = export_zootech_dashboard(
        inputs=ZootechDashboardInputs(data_version=dv, artifacts_dir=tmp_path, scoring_run=sr),
        run_id="dash_test",
        user="tester",
    )
    out_xlsx = run_root / "dashboards" / "zootech_productivity" / "zootech_productivity.xlsx"
    assert out_xlsx.exists()

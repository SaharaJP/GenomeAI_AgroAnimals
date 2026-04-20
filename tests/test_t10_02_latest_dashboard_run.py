from __future__ import annotations

import time
from pathlib import Path

from genomeai.dashboard_director import find_latest_dashboard_run


def test_find_latest_dashboard_run_returns_none_when_missing(tmp_path: Path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    assert find_latest_dashboard_run(artifacts, "dv_none", "director_summary") is None


def test_find_latest_dashboard_run_picks_newest(tmp_path: Path):
    artifacts = tmp_path / "artifacts"
    dv = "dv_x"

    run_a_dir = artifacts / dv / "runs" / "dash_a" / "dashboards" / "director_summary"
    run_b_dir = artifacts / dv / "runs" / "dash_b" / "dashboards" / "director_summary"
    run_a_dir.mkdir(parents=True, exist_ok=True)
    run_b_dir.mkdir(parents=True, exist_ok=True)

    f_a = run_a_dir / "dashboard_summary.json"
    f_b = run_b_dir / "dashboard_summary.json"
    f_a.write_text("{}", encoding="utf-8")
    time.sleep(0.02)
    f_b.write_text("{}", encoding="utf-8")

    assert find_latest_dashboard_run(artifacts, dv, "director_summary") == "dash_b"

from __future__ import annotations

from pathlib import Path

import pandas as pd

from genomeai.marts_timeseries import build_time_series_marts


def test_marts_timeseries_build_smoke(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    input_dir = Path("data/fixtures/target_v2").resolve()
    res = build_time_series_marts(
        artifacts_root=artifacts,
        data_version="dv_demo",
        input_dir=input_dir,
        marts_run="marts_test",
    )
    assert res["ok"] is True

    run_dir = artifacts / "dv_demo" / "marts" / "marts_test"
    assert (run_dir / "cow_day.pkl").exists()
    assert (run_dir / "group_day.pkl").exists()
    assert (run_dir / "lineage_manifest.json").exists()

    cow = pd.read_pickle(run_dir / "cow_day.pkl")
    grp = pd.read_pickle(run_dir / "group_day.pkl")
    assert len(cow) > 0
    assert len(grp) > 0

    # Key columns
    for c in ["farm_id", "animal_id", "date", "is_observed_milkings", "is_observed_sensors"]:
        assert c in cow.columns
    for c in ["farm_id", "pen_id", "date", "headcount"]:
        assert c in grp.columns

    # No duplicate keys in cow_day
    assert cow.duplicated(subset=["farm_id", "animal_id", "date"]).sum() == 0


def test_marts_timeseries_incremental_appends_no_dupes(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    input_dir = Path("data/fixtures/target_v2").resolve()

    # First build
    build_time_series_marts(
        artifacts_root=artifacts,
        data_version="dv_demo",
        input_dir=input_dir,
        marts_run="marts_test",
    )

    run_dir = artifacts / "dv_demo" / "marts" / "marts_test"
    cow1 = pd.read_pickle(run_dir / "cow_day.pkl")

    # Second build with same run id should keep stable (incremental mode)
    build_time_series_marts(
        artifacts_root=artifacts,
        data_version="dv_demo",
        input_dir=input_dir,
        marts_run="marts_test",
    )
    cow2 = pd.read_pickle(run_dir / "cow_day.pkl")

    assert len(cow2) == len(cow1)
    assert cow2.duplicated(subset=["farm_id", "animal_id", "date"]).sum() == 0

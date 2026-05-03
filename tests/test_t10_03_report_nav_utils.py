from __future__ import annotations

from pathlib import Path

from streamlit_app.nav_utils import detect_report_location, list_recent_report_versions


def test_detect_report_location_regular_only(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    dv = "dv_demo"
    rv = "r1"
    (artifacts / dv / "reports_regular" / rv / "exports").mkdir(parents=True)

    res = detect_report_location(artifacts_root=artifacts, data_version=dv, report_version=rv)
    assert res.get("ok") is True
    assert res.get("kind") == "regular"
    assert res.get("regular_exports_dir") is not None


def test_detect_report_location_dashboard_kind(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    dv = "dv_demo"
    rv = "r2"
    (artifacts / dv / "reports" / rv / "dashboard" / "director_summary" / "exports").mkdir(parents=True)

    res = detect_report_location(artifacts_root=artifacts, data_version=dv, report_version=rv)
    assert res.get("ok") is True
    assert res.get("kind") == "dashboard"
    assert "director_summary" in (res.get("dashboard_kinds") or [])


def test_list_recent_report_versions_handles_missing(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    dv = "dv_demo"
    artifacts.mkdir(parents=True)

    res = list_recent_report_versions(artifacts_root=artifacts, data_version=dv, limit=10)
    assert set(res.keys()) == {"regular", "dashboard"}
    assert res["regular"] == []
    assert res["dashboard"] == []

from __future__ import annotations

import json
from pathlib import Path


def test_dashboard_reports_manifest_and_exports(tmp_path: Path):
    from genomeai.dashboard_reports import (
        list_dashboard_reports,
        list_dashboard_report_exports,
        read_dashboard_report_summary,
    )

    artifacts = tmp_path / "artifacts"
    dv = "dv_test"

    # Build minimal saved report layout
    rep_ver = "reportdash_001"
    kind = "director_summary"
    rep_base = artifacts / dv / "reports" / rep_ver / "dashboard" / kind
    exports_dir = rep_base / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    (exports_dir / "snapshot.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (exports_dir / "snapshot.pdf").write_bytes(b"%PDF-1.4")

    summary_path = rep_base / "dashboard_report_summary.json"
    summary_path.write_text(
        json.dumps({"schema": "genomeai.dashboard_report_summary.v1", "report_version": rep_ver}),
        encoding="utf-8",
    )

    meta_dir = artifacts / dv / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = meta_dir / "dashboard_report_manifest.json"
    manifest = {
        "schema": "genomeai.dashboard_report_manifest.v1",
        "data_version": dv,
        "latest": rep_ver,
        "reports": {
            rep_ver: {
                "created_at_utc": "2026-02-04T00:00:00Z",
                "dashboard_run_id": "dash_001",
                "dashboard_kind": kind,
                "summary": str(summary_path),
                "exports_dir": str(exports_dir),
            }
        },
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    res = list_dashboard_reports(artifacts_root=artifacts, data_version=dv, dashboard_kind=kind)
    assert res["ok"] is True
    assert res["latest"] == rep_ver
    assert res["count"] == 1
    assert res["items"][0]["exports_dir"] == str(exports_dir)

    ex = list_dashboard_report_exports(exports_dir=exports_dir)
    assert ex["ok"] is True
    names = {f["name"] for f in ex["files"]}
    assert {"snapshot.png", "snapshot.pdf"}.issubset(names)

    s = read_dashboard_report_summary(summary_path=summary_path)
    assert s["ok"] is True
    assert s["summary"]["schema"] == "genomeai.dashboard_report_summary.v1"

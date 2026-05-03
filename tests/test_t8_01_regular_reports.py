from __future__ import annotations

from pathlib import Path

from genomeai.regular_reports import run_regular_report


def test_regular_reports_smoke(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    dv = "dv_test"

    # No canonical/other module artifacts are required for this smoke test:
    # report generator must be robust and create files with NA sections.
    res = run_regular_report(
        artifacts_root=artifacts_root,
        data_version=dv,
        asof_date="2025-01-31",
        period="daily",
        mode="fallback",
    )
    assert res.get("ok") is True
    report_dir = Path(res["report_dir"])
    assert (report_dir / "fact_pack.json").exists()
    assert (report_dir / "report_summary.json").exists()

    exports = report_dir / "exports"
    assert (exports / "report_director.md").exists()
    assert (exports / "report_ops.md").exists()
    assert (exports / "report_director.html").exists()
    assert (exports / "report_ops.html").exists()
    # PDF может быть NA, но при наличии reportlab обычно создаётся
    assert (exports / "report_director.pdf").exists() or res["outputs"].get("director_pdf") == "NA"

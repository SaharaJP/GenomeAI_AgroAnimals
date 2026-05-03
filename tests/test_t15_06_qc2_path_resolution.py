from __future__ import annotations

from pathlib import Path

from core.application import find_latest_qc2_run, find_latest_qc2_run_dir, resolve_qc2_out_dir
from genomeai.dashboard_vet import load_qc_alerts


DV = "dv_qc2_path_priority"
RUN = "qc2_20990101_000000_priority"


def _write_run(run_dir: Path, *, issue_message: str, alert_message: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text('{"type":"qc2"}\n', encoding="utf-8")
    (run_dir / "qc_issues.csv").write_text(
        "qc_run,data_version,rule_id,dataset,severity,message,remediation,row_id,field,sample_value\n"
        f"{RUN},{DV},rule_x,dm_animals,MAJOR,{issue_message},Fix,row:2,animal_id,dup\n",
        encoding="utf-8",
    )
    (run_dir / "alerts_auto.csv").write_text(
        "alert_id,tenant_id,farm_id,alert_date,severity,alert_type,entity_type,entity_id,message,source_rule_id,qc_run,data_version\n"
        f"al_1,default,farm-1,2099-01-01,MAJOR,QC.GENERIC,farm,,{alert_message},rule_x,{RUN},{DV}\n",
        encoding="utf-8",
    )


def test_t15_06_shared_qc2_resolver_prefers_canonical_layout(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    canonical = artifacts / DV / "qc2" / RUN
    legacy = artifacts / "qc2" / DV / RUN
    _write_run(canonical, issue_message="canonical issue", alert_message="canonical alert")
    _write_run(legacy, issue_message="legacy issue", alert_message="legacy alert")

    latest_name = find_latest_qc2_run(artifacts_root=artifacts, data_version=DV)
    latest_dir = find_latest_qc2_run_dir(artifacts_root=artifacts, data_version=DV)
    resolved = resolve_qc2_out_dir(artifacts_root=artifacts, data_version=DV, qc_run=RUN)

    assert latest_name == RUN
    assert latest_dir == canonical
    assert resolved == canonical



def test_t15_06_dashboard_loader_prefers_canonical_qc2_layout(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    canonical = artifacts / DV / "qc2" / RUN
    legacy = artifacts / "qc2" / DV / RUN
    _write_run(canonical, issue_message="canonical issue", alert_message="canonical alert")
    _write_run(legacy, issue_message="legacy issue", alert_message="legacy alert")

    qr, issues, alerts = load_qc_alerts(artifacts_dir=artifacts, data_version=DV)

    assert qr == RUN
    assert issues.iloc[0]["message"] == "canonical issue"
    assert alerts.iloc[0]["message"] == "canonical alert"

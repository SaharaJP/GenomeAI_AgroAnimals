from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from core.application import load_qc_config_ref
from genomeai.dashboard_vet import load_qc_alerts
from genomeai.qc import run_qc
from genomeai.qc_v2 import run_qc_v2


def _write_csv(root: Path, dv: str, name: str, rows: list[dict]) -> None:
    canonical = root / dv / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(canonical / f"{name}.csv", index=False)


def test_t15_06_qc_v2_writes_unified_report_bundle(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    dv = "dv_qc_v2_bundle"
    _write_csv(artifacts, dv, "dm_farms", [{"farm_id": "F1", "farm_name": "Farm 1"}, {"farm_id": "F1", "farm_name": "Dup"}])
    _write_csv(artifacts, dv, "dm_animals", [{"farm_id": "F1", "animal_id": "A1", "birth_date": "2020-01-01"}])

    res = run_qc_v2(
        artifacts_root=artifacts,
        data_version=dv,
        rules_path=Path("configs/qc_rules_v2.yaml"),
        qc_run="qc2_bundle",
    )

    outputs = res["outputs"]
    assert Path(outputs["qc_report_xlsx"]).exists()
    assert Path(outputs["bad_rows_csv"]).exists()
    assert Path(outputs["qc_issues_csv"]).exists()
    summary = json.loads(Path(outputs["qc_summary_json"]).read_text(encoding="utf-8"))
    assert summary["config_version"] == "2"
    assert "issue_counts" in summary
    assert "row_counts" in summary


def test_t15_06_qc_legacy_uses_shared_report_layout(tmp_path: Path) -> None:
    dv = "dv_qc_legacy_bundle"
    canonical = tmp_path / dv / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)
    base = Path(__file__).resolve().parents[1] / "data" / "examples"
    for fn in ["dm_farms.csv", "dm_animals.csv", "dm_lactations.csv"]:
        (canonical / fn).write_bytes((base / fn).read_bytes())

    # add duplicate PK to force issues
    animals = pd.read_csv(canonical / "dm_animals.csv")
    animals = pd.concat([animals, animals.iloc[[0]]], ignore_index=True)
    animals.to_csv(canonical / "dm_animals.csv", index=False)

    res = run_qc(data_version=dv, artifacts_root=tmp_path)
    outputs = res["outputs"]
    assert Path(outputs["qc_report_xlsx"]).exists()
    assert Path(outputs["bad_rows_csv"]).exists()
    assert Path(outputs["qc_issues_csv"]).exists()
    summary = json.loads(Path(outputs["qc_summary_json"]).read_text(encoding="utf-8"))
    assert summary["config_version"] == "legacy_qc_contracts_v1"
    assert "issue_counts" in summary
    assert "row_counts" in summary


def test_t15_06_dashboard_loader_supports_canonical_qc2_layout(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    dv = "dv_dash_qc2"
    _write_csv(artifacts, dv, "dm_farms", [{"farm_id": "F1", "farm_name": "Farm 1"}])
    _write_csv(artifacts, dv, "dm_animals", [{"farm_id": "F1", "animal_id": "A1", "birth_date": "2020-01-01"}])
    _write_csv(artifacts, dv, "dm_health_events", [{"tenant_id": "default", "event_id": "E1", "animal_id": "A1", "event_date": "2025-03-10", "event_type": "unknown_event"}])

    run_qc_v2(
        artifacts_root=artifacts,
        data_version=dv,
        rules_path=Path("configs/qc_rules_v2.yaml"),
        qc_run="qc2_dash",
    )

    qr, issues, alerts = load_qc_alerts(artifacts_dir=artifacts, data_version=dv)
    assert qr == "qc2_dash"
    assert not issues.empty
    assert "rule_id" in issues.columns
    assert "alert_type" in alerts.columns


def test_t15_06_qc_config_ref_supports_versioned_yaml() -> None:
    cfg = load_qc_config_ref(Path("configs/qc_rules_v2.yaml"))
    assert cfg.config_version == "2"
    assert cfg.format == "yaml"
    assert cfg.rules_count >= 30

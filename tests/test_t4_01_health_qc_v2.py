from __future__ import annotations

from pathlib import Path

import pandas as pd

from genomeai.qc_v2 import run_qc_v2


def test_qc2_health_rules_overlap_and_allowed_values(tmp_path: Path) -> None:
    dv = "dv_health"
    artifacts = tmp_path / "artifacts"
    canonical = artifacts / dv / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)

    # Minimal parents
    pd.DataFrame([{"farm_id": "F1", "farm_name": "Farm 1"}]).to_csv(canonical / "dm_farms.csv", index=False)
    pd.DataFrame(
        [
            {"farm_id": "F1", "animal_id": "A1", "birth_date": "2020-01-01"},
            {"farm_id": "F1", "animal_id": "A2", "birth_date": "2020-01-01"},
        ]
    ).to_csv(canonical / "dm_animals.csv", index=False)

    # Health events
    pd.DataFrame(
        [
            {"tenant_id": "default", "event_id": "HE1", "animal_id": "A1", "event_date": "2025-03-10", "event_type": "mastitis"},
            {"tenant_id": "default", "event_id": "HE2", "animal_id": "A2", "event_date": "2025-03-11", "event_type": "unknown_event"},
        ]
    ).to_csv(canonical / "dm_health_events.csv", index=False)

    # Treatments: overlap for A1 and unknown type for A2
    pd.DataFrame(
        [
            {"tenant_id": "default", "treatment_id": "TR1", "animal_id": "A1", "start_date": "2025-03-10", "end_date": "2025-03-12", "treatment_type": "antibiotic", "reason_event_id": "HE1", "withdrawal_end_date": ""},
            {"tenant_id": "default", "treatment_id": "TR2", "animal_id": "A1", "start_date": "2025-03-12", "end_date": "2025-03-15", "treatment_type": "vitamin", "reason_event_id": "HE1", "withdrawal_end_date": ""},
            {"tenant_id": "default", "treatment_id": "TR3", "animal_id": "A2", "start_date": "2025-03-11", "end_date": "", "treatment_type": "unknown_treat", "reason_event_id": "HE2", "withdrawal_end_date": ""},
        ]
    ).to_csv(canonical / "dm_treatments.csv", index=False)

    # Lactations to exercise join_date_order (calving before birth -> violation)
    pd.DataFrame(
        [{"farm_id": "F1", "animal_id": "A1", "lactation_id": "L1", "calving_date": "2019-12-31"}]
    ).to_csv(canonical / "dm_lactations.csv", index=False)

    res = run_qc_v2(
        data_version=dv,
        artifacts_root=artifacts,
        rules_path=Path("configs/qc_rules_v2.yaml"),
        qc_run="qc2_health",
    )

    issues = pd.read_csv(res["outputs"]["qc_issues_csv"])
    assert len(issues) >= 1

    # No unknown types after implementing missing rule types
    assert not issues["message"].astype(str).str.contains("Unknown rule type", na=False).any()

    # Overlap should be detected (TR1/TR2 overlap at 2025-03-12 inclusive)
    assert (issues["rule_id"] == "treatments_overlap").any()

    # Allowed values should detect unknown types
    assert (issues["rule_id"] == "health_events_type_allowed").any() or (issues["rule_id"] == "treatments_type_allowed").any()

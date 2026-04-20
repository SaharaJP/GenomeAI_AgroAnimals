from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from genomeai.repro_kpi_worklist import compute_repro


def _write(df: pd.DataFrame, p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)


def test_repro_worklists_and_kpis(tmp_path: Path) -> None:
    # Synthetic Target v2 tables
    animals = pd.DataFrame(
        [
            {"tenant_id": "t1", "farm_id": "f1", "animal_id": "c1"},
            {"tenant_id": "t1", "farm_id": "f1", "animal_id": "c2"},
            {"tenant_id": "t1", "farm_id": "f1", "animal_id": "c3"},
            {"tenant_id": "t1", "farm_id": "f1", "animal_id": "c4"},
        ]
    )
    lact = pd.DataFrame(
        [
            {"tenant_id": "t1", "farm_id": "f1", "animal_id": "c1", "lactation_id": "c1__1", "lactation_no": 1, "calving_date": "2025-01-01"},
            {"tenant_id": "t1", "farm_id": "f1", "animal_id": "c2", "lactation_id": "c2__1", "lactation_no": 1, "calving_date": "2025-01-01"},
            {"tenant_id": "t1", "farm_id": "f1", "animal_id": "c3", "lactation_id": "c3__1", "lactation_no": 1, "calving_date": "2025-01-01"},
            {"tenant_id": "t1", "farm_id": "f1", "animal_id": "c4", "lactation_id": "c4__1", "lactation_no": 1, "calving_date": "2025-01-01"},
        ]
    )

    repro = pd.DataFrame(
        [
            # c2: service but no preg check => diagnostics
            {"tenant_id": "t1", "farm_id": "f1", "animal_id": "c2", "event_date": "2025-02-01", "event_type": "insemination", "result": ""},
            # c3: service + negative preg check => repeat
            {"tenant_id": "t1", "farm_id": "f1", "animal_id": "c3", "event_date": "2025-02-01", "event_type": "insemination", "result": ""},
            {"tenant_id": "t1", "farm_id": "f1", "animal_id": "c3", "event_date": "2025-03-05", "event_type": "preg_diagnosis", "result": "negative"},
            # c4: service + positive preg check => pregnant
            {"tenant_id": "t1", "farm_id": "f1", "animal_id": "c4", "event_date": "2025-02-01", "event_type": "insemination", "result": ""},
            {"tenant_id": "t1", "farm_id": "f1", "animal_id": "c4", "event_date": "2025-03-05", "event_type": "preg_diagnosis", "result": "positive"},
        ]
    )

    _write(animals, tmp_path / "dm_animals.csv")
    _write(lact, tmp_path / "dm_lactations.csv")
    _write(repro, tmp_path / "dm_repro_events.csv")

    cfg = {
        "defaults": {
            "voluntary_waiting_period_days": 50,
            "preg_check_due_days": 32,
            "repeat_due_days_if_negative": 1,
            "repeat_due_days_no_check": 60,
            "lookback_conception_days": 60,
            "lookback_pregnancy_rate_days": 21,
        },
        "parsing": {
            "insemination_event_type_contains": ["insemin"],
            "pregcheck_event_type_contains": ["preg"],
            "pregnant_result_values": ["positive"],
            "not_pregnant_result_values": ["negative"],
        },
        "worklists": {
            "insemination_priority_by_dim": [{"min_dim": 0, "priority": 5}],
            "diagnostics_priority_by_days_since_service": [{"min_days": 0, "priority": 5}],
            "repeat_priority_by_days_since_service": [{"min_days": 0, "priority": 5}],
        },
    }

    asof = date(2025, 3, 10)
    kpis_df, wl_df, cows_df = compute_repro(input_dir=tmp_path, asof_date=asof, cfg=cfg)

    # Worklists: c1 insemination, c2 diagnostics, c3 repeat
    assert set(wl_df["animal_id"].astype(str).tolist()) == {"c1", "c2", "c3"}
    m = dict(zip(wl_df["animal_id"].astype(str).tolist(), wl_df["worklist_type"].tolist()))
    assert m["c1"] == "insemination"
    assert m["c2"] == "diagnostics"
    assert m["c3"] == "repeat"

    # Pregnancy mapping: c4 pregnant, days_open = 31
    c4 = cows_df[cows_df["animal_id"].astype(str) == "c4"].iloc[0]
    assert bool(c4["pregnant"]) is True
    assert int(c4["days_open"]) == 31

    # Conception rate in 60d: one successful service out of three services (c2,c3,c4) => 1/3
    k = kpis_df.set_index("kpi_id")["value"].to_dict()
    assert abs(float(k["repro_conception_rate_60d"]) - (1.0 / 3.0)) < 1e-6
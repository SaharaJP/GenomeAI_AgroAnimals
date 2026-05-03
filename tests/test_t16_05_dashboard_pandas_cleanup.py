from __future__ import annotations

import hashlib
import warnings
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from genomeai.dashboard_director import compute_milk_trend, compute_milk_trend_windows, export_director_summary, DirectorSummaryInputs, load_kpi_dictionary
from genomeai.dashboard_insights import compute_top_deviations, compute_milk_trend_exceptions, load_trend_exceptions_rules
from genomeai.dashboard_vet import compute_withdrawal_windows
from genomeai.dashboard_zootech import compute_group_analytics
from genomeai.kpi_targets import compute_plan_fact, load_kpi_targets
from genomeai.kpi_v2 import run_kpi


EXPECTED_MILK_TREND_SHA256 = "d398d78b98804fc46c9713abb11f6092b305a46c717a5dcb9bd96eb506dff9d5"
EXPECTED_MILK_WINDOWS_SHA256 = "06ce4db4a7ab6a67854feb93d05df4bc412ee2e4f274eca918002f92bc7a2581"
EXPECTED_TOP_DEVIATIONS_SHA256 = "de097ec211555f6eee9f573da277d299b1136aceb2afcf834a4f0f0a04069d00"
EXPECTED_GROUP_STATS_SHA256 = "68873e69cabbdbbf450142680e7640f0a97de62de33840107bbc56412d16b366"
EXPECTED_OUTLIERS_SHA256 = "67621ed451902323036520387c43628bdaf4f864faed1f6debc3c3b02398c736"
EXPECTED_PRIORITY_SHA256 = "6c95e1d8421f00f34816bc4eb7c8509408f19b1b9bd7ec0d7d60466ebe6216cb"
EXPECTED_CULL_SHA256 = "e61e2fd5a8400d1a260938987f155c3073501b580d615789e7ee6f2cbd90052f"
EXPECTED_WITHDRAWAL_SHA256 = "bc84aa473a8e1deadb36aceb20d921565784a776c92423eb7ed83bb7c918ae4f"


def _stable_df_hash(df: pd.DataFrame) -> str:
    if df.empty:
        payload = "EMPTY|" + "|".join(map(str, df.columns))
    else:
        ordered = df.copy()
        ordered = ordered.reindex(sorted(ordered.columns.astype(str)), axis=1)
        try:
            ordered = ordered.sort_values(list(ordered.columns.astype(str))).reset_index(drop=True)
        except Exception:
            ordered = ordered.reset_index(drop=True)
        payload = ordered.fillna("<NA>").to_csv(index=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_t16_05_director_helpers_are_warning_free_and_hash_stable() -> None:
    fixtures = Path("data/fixtures/target_v2")
    asof = datetime.strptime("2025-01-05", "%Y-%m-%d").date()

    targets_cfg = load_kpi_targets(cfg_path=Path("configs/kpi/kpi_targets_v1.yaml"), override_dir=None)
    kpi_cfg = load_kpi_dictionary(Path("configs/kpi/kpi_v2.yaml"))
    rules = load_trend_exceptions_rules(Path("configs/kpi/kpi_trend_exceptions_v1.yaml"))

    kpi_long = pd.DataFrame(
        [
            {"tenant_id": "default", "farm_id": "FARM_001", "kpi_id": "milk_total_kg_7d", "value": 110000, "unit": "kg"},
            {"tenant_id": "default", "farm_id": "FARM_001", "kpi_id": "scc_avg_7d", "value": 220000, "unit": "cells/ml"},
        ]
    )

    with warnings.catch_warnings():
        warnings.filterwarnings("error", category=pd.errors.SettingWithCopyWarning)
        milk_trend = compute_milk_trend(input_dir=fixtures, days=90, asof=asof)
        milk_windows = compute_milk_trend_windows(input_dir=fixtures, asof=asof, windows=(7, 30, 90))
        plan_fact = compute_plan_fact(kpi_long, targets_cfg=targets_cfg, data_version="dv_x", kpi_run_id="kpi_x")
        top_devs = compute_top_deviations(plan_fact, kpi_cfg=kpi_cfg, top_n=10)
        milk_exceptions = compute_milk_trend_exceptions(milk_windows, rules=rules, data_version="dv_x", dashboard_run_id="dash_x")

    assert _stable_df_hash(milk_trend) == EXPECTED_MILK_TREND_SHA256
    assert _stable_df_hash(milk_windows) == EXPECTED_MILK_WINDOWS_SHA256
    assert _stable_df_hash(top_devs) == EXPECTED_TOP_DEVIATIONS_SHA256
    assert milk_exceptions.empty



def test_t16_05_director_export_snapshot_artifacts_preserved_without_settingwithcopy(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    dv = "dv_t16_05_dash"

    run_kpi(
        data_version=dv,
        asof_date="2025-01-05",
        input_dir=Path("data/fixtures/target_v2"),
        artifacts_root=artifacts,
        config_kpi=Path("configs/kpi/kpi_v2.yaml"),
        config_thresholds=Path("configs/kpi/kpi_thresholds_v2.yaml"),
        run_id="kpi_test",
    )

    inputs = DirectorSummaryInputs(
        data_version=dv,
        artifacts_dir=artifacts,
        input_dir=Path("data/fixtures/target_v2"),
        kpi_run_id="kpi_test",
        asof_date=datetime.strptime("2025-01-05", "%Y-%m-%d").date(),
    )

    with warnings.catch_warnings():
        warnings.filterwarnings("error", category=pd.errors.SettingWithCopyWarning)
        run_root = export_director_summary(inputs=inputs, run_id="dash_test")

    out_dir = run_root / "dashboards" / "director_summary"
    assert (out_dir / "director_summary.xlsx").exists()
    assert (out_dir / "director_summary.png").exists()
    assert (out_dir / "milk_trend_90d.csv").exists()
    assert (out_dir / "milk_trend_windows.csv").exists()
    assert (out_dir / "milk_trend_exceptions.csv").exists()

    trend = pd.read_csv(out_dir / "milk_trend_90d.csv")
    windows = pd.read_csv(out_dir / "milk_trend_windows.csv")
    assert _stable_df_hash(trend) == EXPECTED_MILK_TREND_SHA256
    assert _stable_df_hash(windows) == EXPECTED_MILK_WINDOWS_SHA256



def test_t16_05_zootech_views_are_warning_free_and_outputs_stable() -> None:
    scored = pd.DataFrame(
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

    with warnings.catch_warnings():
        warnings.filterwarnings("error", category=pd.errors.SettingWithCopyWarning)
        analytics = compute_group_analytics(scored)

    assert _stable_df_hash(analytics["group_stats"]) == EXPECTED_GROUP_STATS_SHA256
    assert _stable_df_hash(analytics["outliers"]) == EXPECTED_OUTLIERS_SHA256
    assert _stable_df_hash(analytics["priority"]) == EXPECTED_PRIORITY_SHA256
    assert analytics["observe"].empty
    assert _stable_df_hash(analytics["cull"]) == EXPECTED_CULL_SHA256



def test_t16_05_vet_views_are_warning_free_and_outputs_stable() -> None:
    tr = pd.DataFrame(
        [
            {
                "treatment_id": "TR1",
                "animal_id": "A1",
                "start_date": "2025-03-10",
                "end_date": "2025-03-12",
                "treatment_type": "antibiotic",
            },
            {
                "treatment_id": "TR2",
                "animal_id": "A2",
                "start_date": "2025-03-01",
                "end_date": "",
                "treatment_type": "unknown_type",
            },
        ]
    )
    rules = {
        "default_withdrawal_days": 7,
        "treatment_types": {"antibiotic": {"withdrawal_days": 10}},
    }

    with warnings.catch_warnings():
        warnings.filterwarnings("error", category=pd.errors.SettingWithCopyWarning)
        out = compute_withdrawal_windows(tr, asof_date=date(2025, 3, 15), rules=rules)

    selected = out[
        [
            "treatment_id",
            "animal_id",
            "withdrawal_days_rule",
            "last_admin_date",
            "withdrawal_end_date_calc",
            "withdrawal_end_date_effective",
            "withdrawal_active_asof",
        ]
    ].copy()
    assert _stable_df_hash(selected) == EXPECTED_WITHDRAWAL_SHA256

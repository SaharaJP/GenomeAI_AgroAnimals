import pandas as pd
import numpy as np

from genomeai.mastitis_risk import _build_labels_from_health_events, _apply_fallback_label_from_scc, time_based_split


def test_label_from_health_events_horizon():
    cow_day = pd.DataFrame(
        {
            "farm_id": ["F1"] * 5,
            "animal_id": ["A1"] * 5,
            "date": pd.to_datetime(["2025-01-01","2025-01-02","2025-01-03","2025-01-04","2025-01-05"]),
        }
    )
    health_events = pd.DataFrame(
        {
            "farm_id": ["F1"],
            "animal_id": ["A1"],
            "event_date": ["2025-01-04"],
            "condition_code": ["MASTITIS"],
        }
    )
    y, meta = _build_labels_from_health_events(cow_day, health_events, horizon_days=2, mastitis_codes=["MASTITIS"])
    # For date=2025-01-02, window is (02,04] => includes 04 => y=1
    assert int(y.iloc[1]) == 1
    # For date=2025-01-03, window (03,05] includes 04 => y=1
    assert int(y.iloc[2]) == 1
    # For date=2025-01-04, window (04,06] excludes 04 itself => y=0
    assert int(y.iloc[3]) == 0
    assert meta["label_source"] == "health_events"


def test_fallback_label_from_scc_future_spike():
    cow_day = pd.DataFrame(
        {
            "farm_id": ["F1"] * 5,
            "animal_id": ["A1"] * 5,
            "date": pd.to_datetime(["2025-01-01","2025-01-02","2025-01-03","2025-01-04","2025-01-05"]),
            "scc_cells_ml": [100000, 120000, 130000, 600000, 110000],
        }
    )
    y, meta = _apply_fallback_label_from_scc(cow_day, horizon_days=2, scc_high=500000)
    # spike at 2025-01-04 -> should label 2025-01-02 and 2025-01-03 positive (in next 2 days)
    assert int(y.iloc[1]) == 1
    assert int(y.iloc[2]) == 1
    assert int(y.iloc[3]) == 0


def test_time_split_anti_leakage_gap():
    X = pd.DataFrame({"x":[1]*100})
    y = pd.Series([0]*100)
    dates = pd.date_range("2025-01-01", periods=100, freq="D")
    train_idx, test_idx, meta = time_based_split(X, y, dates=pd.Series(dates), horizon_days=7, test_fraction=0.2)
    max_train = pd.to_datetime(pd.Series(dates).iloc[train_idx]).max()
    min_test = pd.to_datetime(pd.Series(dates).iloc[test_idx]).min()
    assert max_train + pd.Timedelta(days=7) < min_test

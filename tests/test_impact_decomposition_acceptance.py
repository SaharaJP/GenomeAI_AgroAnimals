"""§P3-1 acceptance — table 3.5.5 of the diploma.

Locks the verdict that, after additive K(t)=T+S+E+ε decomposition before
Welch t-test, 4 of the 5 mastitis events show significant milk drop
(p<0.05) and EV_3002_MAST_01 does NOT (mild form).

Reads `data/demo/investor_v1/milk_yields.json` and `dm_health_events.csv`
directly so the test stays portable independently of the
`/tmp/thesis_validation/` validation workdir.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from web_cabinet.ai.impact_decomposition import decompose_for_welch


_DEMO = Path(__file__).resolve().parents[1] / "data" / "demo" / "investor_v1"


def _load_event_metadata():
    """Load the 5 mastitis events used in table 3.5.5."""
    events_df = pd.read_csv(_DEMO / "dm_health_events.csv")
    mast = events_df[events_df["event_type"].astype(str).str.lower() == "mastitis"].copy()
    mast["event_date"] = pd.to_datetime(mast["event_date"]).dt.date
    return mast.head(5)


def _load_milk_yields_for_cow(cow_id: str):
    """Return (dates, milk_kg) sorted by date for the given cow."""
    raw = json.load(open(_DEMO / "milk_yields.json"))
    rows = [r for r in raw if str(r["animal_id"]) == str(cow_id)]
    rows.sort(key=lambda r: r["date"])
    dates = [datetime.date.fromisoformat(r["date"][:10]) for r in rows]
    values = [float(r["milk_kg"]) for r in rows]
    return dates, values


def _decomposed_welch(cow_id: str, event_date: datetime.date) -> dict:
    dates, values = _load_milk_yields_for_cow(cow_id)
    pre, post = decompose_for_welch(values, dates, event_date, window_days=14)
    if len(pre) < 3 or len(post) < 3:
        pytest.fail(f"too few points for {cow_id} {event_date}: pre={len(pre)} post={len(post)}")
    t, pval = stats.ttest_ind(pre, post, equal_var=False)
    return {
        "n_pre": int(len(pre)),
        "n_post": int(len(post)),
        "t_stat": float(t),
        "p_value": float(pval),
        "delta_adj": float(post.mean() - pre.mean()),
        "significant": pval < 0.05,
    }


# ── per-event acceptance tests ────────────────────────────────────────────


@pytest.mark.parametrize("cow,event_date,event_id", [
    ("4821", datetime.date(2026, 3, 10), "EV_4821_MAST_01"),
    ("3891", datetime.date(2026, 2, 20), "EV_3891_MAST_01"),
    ("3891", datetime.date(2026, 3, 22), "EV_3891_MAST_02"),
    ("3010", datetime.date(2026, 4,  7), "EV_3010_MAST_01"),
])
def test_severe_mastitis_events_are_significant_after_decomposition(cow, event_date, event_id):
    """4 severe-form events must remain significant (p<0.05) after decomposition."""
    r = _decomposed_welch(cow, event_date)
    assert r["significant"], (
        f"{event_id}: expected significant drop after decomposition, "
        f"got p={r['p_value']:.4f} (delta_adj={r['delta_adj']:+.2f})"
    )
    assert r["delta_adj"] < 0, f"{event_id}: drop direction must be negative"


def test_mild_mastitis_event_3002_is_not_significant_after_decomposition():
    """EV_3002_MAST_01 (mild form) must remain not-significant per table 3.5.5."""
    r = _decomposed_welch("3002", datetime.date(2026, 2, 10))
    assert not r["significant"], (
        f"EV_3002_MAST_01: expected NOT significant (mild form), "
        f"got p={r['p_value']:.4f} (delta_adj={r['delta_adj']:+.2f})"
    )


def test_aggregate_table_3_5_5_verdict():
    """Aggregate: 4/5 significant + EV_3002 not significant."""
    cases = [
        ("4821", datetime.date(2026, 3, 10), True),
        ("3891", datetime.date(2026, 2, 20), True),
        ("3891", datetime.date(2026, 3, 22), True),
        ("3002", datetime.date(2026, 2, 10), False),
        ("3010", datetime.date(2026, 4,  7), True),
    ]
    n_significant = 0
    for cow, ed, expected_sig in cases:
        r = _decomposed_welch(cow, ed)
        assert r["significant"] == expected_sig, (
            f"{cow} {ed}: expected sig={expected_sig}, got p={r['p_value']:.4f}"
        )
        if r["significant"]:
            n_significant += 1
    assert n_significant == 4, f"expected 4/5 significant, got {n_significant}/5"

"""Attention-cow detection: flags cows needing immediate action."""
from __future__ import annotations

import datetime
from typing import Any

import pandas as pd

from web_cabinet.ai.context_helpers.demo_loader import DemoDataStore


def flag_attention_cows(
    store: DemoDataStore,
    farm_id: str,
    as_of: datetime.date,
    period_days: int = 7,
) -> list[dict]:
    """
    Return list of {cow_id, name, flags, details} for cows needing attention.
    Flags: falling_yield, active_treatment, missed_heat, high_scc,
           post_mastitis, ready_for_culling, overdue_preg_check.
    """
    as_ts = pd.Timestamp(as_of)
    window_start = as_ts - pd.Timedelta(days=period_days)

    animals = store.animals()
    if animals.empty:
        return []

    # Build base animal map
    animal_map: dict[str, dict] = {}
    for _, row in animals.iterrows():
        animal_map[str(row["animal_id"])] = {
            "cow_id": str(row["animal_id"]),
            "name": str(row.get("name", row["animal_id"])),
            "flags": [],
            "details": {},
        }

    _flag_falling_yield(store, animal_map, as_ts, window_start)
    _flag_active_treatment(store, animal_map, as_ts)
    _flag_high_scc(store, animal_map, as_ts)
    _flag_post_mastitis(store, animal_map, as_ts, window_start)
    _flag_missed_heat(store, animal_map, as_ts, window_start)
    _flag_ready_for_culling(store, animal_map)
    _flag_overdue_preg_check(store, animal_map, as_ts, window_start)

    return [v for v in animal_map.values() if v["flags"]]


# ------------------------------------------------------------------
# per-flag helpers
# ------------------------------------------------------------------

def _flag_falling_yield(
    store: DemoDataStore,
    animal_map: dict,
    as_ts: pd.Timestamp,
    window_start: pd.Timestamp,
) -> None:
    milkings = store.milkings()
    if milkings.empty or "milk_kg" not in milkings.columns:
        return
    mk = milkings.copy()
    mk["date"] = pd.to_datetime(mk["date"], errors="coerce")

    for cow_id in list(animal_map.keys()):
        cow_mk = mk[mk["animal_id"] == cow_id].sort_values("date")
        if len(cow_mk) < 2:
            continue
        recent = cow_mk[cow_mk["date"] >= window_start]["milk_kg"]
        earlier = cow_mk[cow_mk["date"] < window_start]["milk_kg"]
        if recent.empty or earlier.empty:
            continue
        avg_recent = recent.mean()
        avg_earlier = earlier.mean()
        if avg_earlier > 0 and (avg_earlier - avg_recent) / avg_earlier > 0.10:
            animal_map[cow_id]["flags"].append("falling_yield")
            animal_map[cow_id]["details"]["yield_drop_pct"] = round(
                (avg_earlier - avg_recent) / avg_earlier * 100, 1
            )


def _flag_active_treatment(
    store: DemoDataStore,
    animal_map: dict,
    as_ts: pd.Timestamp,
) -> None:
    treatments = store.treatments()
    if treatments.empty:
        return
    tr = treatments.copy()
    tr["start_date"] = pd.to_datetime(tr["start_date"], errors="coerce")
    tr["end_date"] = pd.to_datetime(tr["end_date"], errors="coerce")
    active = tr[(tr["start_date"] <= as_ts) & (tr["end_date"] >= as_ts)]
    for cow_id in active["animal_id"].astype(str).unique():
        if cow_id in animal_map:
            animal_map[cow_id]["flags"].append("active_treatment")


def _flag_high_scc(
    store: DemoDataStore,
    animal_map: dict,
    as_ts: pd.Timestamp,
) -> None:
    milkings = store.milkings()
    if milkings.empty or "scc_cells_ml" not in milkings.columns:
        return
    mk = milkings.copy()
    mk["date"] = pd.to_datetime(mk["date"], errors="coerce")
    window = as_ts - pd.Timedelta(days=7)
    recent = mk[mk["date"] >= window]
    agg = recent.groupby("animal_id")["scc_cells_ml"].mean()
    for cow_id, scc in agg.items():
        if str(cow_id) in animal_map and scc > 200_000:
            animal_map[str(cow_id)]["flags"].append("high_scc")
            animal_map[str(cow_id)]["details"]["scc_avg_k"] = round(float(scc) / 1000, 1)


def _flag_post_mastitis(
    store: DemoDataStore,
    animal_map: dict,
    as_ts: pd.Timestamp,
    window_start: pd.Timestamp,
) -> None:
    he = store.health_events()
    if he.empty:
        return
    he = he.copy()
    he["event_date"] = pd.to_datetime(he["event_date"], errors="coerce")
    mastitis = he[
        (he["event_type"].str.lower() == "mastitis")
        & (he["event_date"] >= window_start)
        & (he["event_date"] <= as_ts)
    ]
    for cow_id in mastitis["animal_id"].astype(str).unique():
        if cow_id in animal_map and "active_treatment" not in animal_map[cow_id]["flags"]:
            animal_map[cow_id]["flags"].append("post_mastitis")


def _flag_missed_heat(
    store: DemoDataStore,
    animal_map: dict,
    as_ts: pd.Timestamp,
    window_start: pd.Timestamp,
) -> None:
    repro = store.repro_events()
    if repro.empty:
        return
    repro = repro.copy()
    repro["event_date"] = pd.to_datetime(repro["event_date"], errors="coerce")
    missed = repro[
        (repro["event_type"] == "heat")
        & (repro["result"].str.lower().isin(["missed", "no_action", "candidate"]))
        & (repro["event_date"] >= window_start)
    ]
    for cow_id in missed["animal_id"].astype(str).unique():
        if cow_id in animal_map:
            animal_map[cow_id]["flags"].append("missed_heat")


def _flag_ready_for_culling(
    store: DemoDataStore,
    animal_map: dict,
) -> None:
    decisions = store.decisions()
    if decisions.empty:
        return
    if "recommendation_type" not in decisions.columns:
        return
    cull = decisions[
        decisions["recommendation_type"].str.lower().isin(["cull", "culling"])
        & decisions.get("decision", pd.Series(dtype=str)).isin(["accept", "defer", ""])
    ] if "decision" in decisions.columns else decisions[
        decisions["recommendation_type"].str.lower().isin(["cull", "culling"])
    ]
    for cow_id in cull.get("animal_id", pd.Series(dtype=str)).astype(str).unique():
        if cow_id in animal_map:
            animal_map[cow_id]["flags"].append("ready_for_culling")


def _flag_overdue_preg_check(
    store: DemoDataStore,
    animal_map: dict,
    as_ts: pd.Timestamp,
    window_start: pd.Timestamp,
) -> None:
    repro = store.repro_events()
    if repro.empty:
        return
    repro = repro.copy()
    repro["event_date"] = pd.to_datetime(repro["event_date"], errors="coerce")
    due = repro[
        (repro["event_type"] == "preg_check_due")
        & (repro["event_date"] <= as_ts)
        & (repro["event_date"] >= window_start - pd.Timedelta(days=14))
    ]
    for cow_id in due["animal_id"].astype(str).unique():
        if cow_id in animal_map:
            animal_map[cow_id]["flags"].append("overdue_preg_check")

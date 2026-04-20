from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from .versioning import (
    generate_run_id,
    get_run_root,
    write_checksums,
    write_json,
    write_run_manifest,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_table(input_dir: Path, name: str) -> pd.DataFrame:
    """Read dm_*.csv (preferred) or dm_*.parquet if present."""
    input_dir = Path(input_dir)
    pqt = input_dir / f"{name}.parquet"
    if pqt.exists():
        try:
            return pd.read_parquet(pqt)
        except Exception:
            pass
    csv = input_dir / f"{name}.csv"
    if not csv.exists():
        return pd.DataFrame()
    return pd.read_csv(csv)


def _to_dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def _ensure_date_col(df: pd.DataFrame, col: str) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return df
    out = df.copy()
    out[col] = _to_dt(out[col]).dt.floor("D")
    return out


def _infer_last_built_date(existing_cow_day: Path) -> Optional[pd.Timestamp]:
    if not existing_cow_day.exists():
        return None
    try:
        if existing_cow_day.suffix == ".pkl":
            df = pd.read_pickle(existing_cow_day)
        else:
            df = pd.read_csv(existing_cow_day)
        if "date" not in df.columns or df.empty:
            return None
        return pd.to_datetime(df["date"], errors="coerce").max()
    except Exception:
        return None


def _build_cow_day(
    *,
    input_dir: Path,
    start_after: Optional[pd.Timestamp] = None,
) -> pd.DataFrame:
    """Build cow_day mart from daily milkings + daily sensors.

    Rules (v1):
      - Join keys: farm_id + animal_id + date.
      - Units assumed canonical: milk_kg, activity_steps, rumination_min, body_temp_c.
      - Missing handling:
          * Keep a dense daily grid per animal between min/max observed date (from either milkings or sensors).
          * Add flags is_observed_milkings/is_observed_sensors.
          * Provide short-gap forward-fill (limit=3 days) for select numeric columns into *_ffill3.
    """
    milk = _read_table(input_dir, "dm_milkings_daily")
    sens = _read_table(input_dir, "dm_sensors_daily")
    animals = _read_table(input_dir, "dm_animals")

    milk = _ensure_date_col(milk, "date")
    sens = _ensure_date_col(sens, "date")

    # NOTE: farm_id may be missing in dm_* inputs. Later we enrich it from dm_animals (Target v2 fixtures).

    # Select minimal columns (v1)
    milk_cols = [
        c
        for c in [
            "farm_id",
            "animal_id",
            "lactation_id",
            "date",
            "dim",
            "milk_kg",
            "fat_pct",
            "protein_pct",
            "scc_cells_ml",
        ]
        if c in milk.columns
    ]
    sens_cols = [
        c
        for c in [
            "tenant_id",
            "farm_id",
            "animal_id",
            "date",
            "lactation_id",
            "dim",
            "activity_steps",
            "activity_count",
            "steps",
            "rumination_min",
            "body_temp_c",
            "temperature_c",
            "temp_c",
        ]
        if c in sens.columns
    ]
    milk = milk[milk_cols].copy() if not milk.empty else pd.DataFrame(columns=milk_cols)
    sens = sens[sens_cols].copy() if not sens.empty else pd.DataFrame(columns=sens_cols)

    # Normalize sensor column names to canonical (v1)
    if not sens.empty:
        if "activity_steps" not in sens.columns:
            if "activity_count" in sens.columns:
                sens["activity_steps"] = sens["activity_count"]
            elif "steps" in sens.columns:
                sens["activity_steps"] = sens["steps"]
        if "body_temp_c" not in sens.columns:
            if "temperature_c" in sens.columns:
                sens["body_temp_c"] = sens["temperature_c"]
            elif "temp_c" in sens.columns:
                sens["body_temp_c"] = sens["temp_c"]

    # Some sources may omit farm_id. In Target v2 fixtures, farm_id lives in dm_animals.
    if (not animals.empty) and ("farm_id" in animals.columns) and ("animal_id" in animals.columns):
        a_cols = [c for c in ["tenant_id", "animal_id", "farm_id"] if c in animals.columns]
        amap = animals[a_cols].drop_duplicates(subset=[c for c in ["tenant_id", "animal_id"] if c in a_cols])

        def _add_farm_id(df: pd.DataFrame) -> pd.DataFrame:
            if df.empty:
                return df
            if "farm_id" in df.columns:
                return df
            join_keys = [k for k in ["tenant_id", "animal_id"] if k in df.columns and k in amap.columns]
            if not join_keys:
                # fallback: join only by animal_id
                if "animal_id" in df.columns and "animal_id" in amap.columns:
                    join_keys = ["animal_id"]
            if join_keys:
                out = df.merge(amap, on=join_keys, how="left")
            else:
                out = df.copy()
                out["farm_id"] = pd.NA
            return out

        milk = _add_farm_id(milk)
        sens = _add_farm_id(sens)

    # Ensure farm_id column exists for stable keys.
    if not milk.empty and "farm_id" not in milk.columns:
        milk["farm_id"] = pd.NA
    if not sens.empty and "farm_id" not in sens.columns:
        sens["farm_id"] = pd.NA

    for df in [milk, sens]:
        if df.empty:
            continue
        for c in ["milk_kg", "fat_pct", "protein_pct", "scc_cells_ml", "activity_steps", "rumination_min", "body_temp_c", "dim"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")

    if milk.empty and sens.empty:
        return pd.DataFrame()

    # Determine per-animal date ranges
    parts = []
    if not milk.empty:
        parts.append(milk[["farm_id", "animal_id", "date"]].dropna())
    if not sens.empty:
        parts.append(sens[["farm_id", "animal_id", "date"]].dropna())
    idx_base = pd.concat(parts, ignore_index=True)
    if start_after is not None:
        idx_base = idx_base[idx_base["date"] > start_after]
        if idx_base.empty:
            return pd.DataFrame()

    # Dense grid between min/max per animal
    ranges = (
        idx_base.groupby(["farm_id", "animal_id"], dropna=False)["date"]
        .agg(["min", "max"])
        .reset_index()
    )
    grids = []
    for _, r in ranges.iterrows():
        d0 = r["min"]
        d1 = r["max"]
        if pd.isna(d0) or pd.isna(d1):
            continue
        dr = pd.date_range(d0, d1, freq="D")
        g = pd.DataFrame({"farm_id": r["farm_id"], "animal_id": r["animal_id"], "date": dr})
        grids.append(g)
    grid = pd.concat(grids, ignore_index=True) if grids else idx_base.drop_duplicates()

    out = grid

    # Merge inputs
    if not milk.empty:
        out = out.merge(milk, on=[c for c in ["farm_id", "animal_id", "date"] if c in milk.columns], how="left", suffixes=("", "_milk"))
        out["is_observed_milkings"] = out["milk_kg"].notna() if "milk_kg" in out.columns else False
    else:
        out["is_observed_milkings"] = False

    if not sens.empty:
        out = out.merge(
            sens,
            on=[c for c in ["farm_id", "animal_id", "date"] if c in sens.columns],
            how="left",
            suffixes=("", "_sens"),
        )
        # prefer lactation_id/dim from milkings if present
        for c in ["lactation_id", "dim"]:
            c_s = f"{c}_sens"
            if c_s in out.columns and c in out.columns:
                out[c] = out[c].fillna(out[c_s])
                out = out.drop(columns=[c_s])
        out["is_observed_sensors"] = out["activity_steps"].notna() if "activity_steps" in out.columns else False
    else:
        out["is_observed_sensors"] = False

    # Deterministic ordering
    out = out.sort_values(["farm_id", "animal_id", "date"], kind="mergesort").reset_index(drop=True)

    # Short-gap forward fill to support first ML features and simple charts.
    ffill_cols = [c for c in ["milk_kg", "activity_steps", "rumination_min", "body_temp_c"] if c in out.columns]
    for c in ffill_cols:
        out[f"{c}_ffill3"] = (
            out.groupby(["farm_id", "animal_id"], dropna=False)[c]
            .apply(lambda s: s.ffill(limit=3))
            .reset_index(level=[0, 1], drop=True)
        )
        out[f"{c}_imputed_ffill3"] = out[f"{c}_ffill3"].notna() & out[c].isna()

    return out


def _build_group_day(
    *,
    cow_day: pd.DataFrame,
    input_dir: Path,
) -> pd.DataFrame:
    """Aggregate cow_day to group_day using pen assignment from dm_pen_moves.

    Rules (v1):
      - group key = pen_id (from dm_pen_moves.to_pen_id as of date).
      - Aggregate daily metrics: sum_milk_kg, avg_milk_kg, headcount.
      - Missingness: pct_missing_milkings, pct_missing_sensors.
    """
    if cow_day.empty:
        return pd.DataFrame()

    moves = _read_table(input_dir, "dm_pen_moves")
    animals = _read_table(input_dir, "dm_animals")
    if moves.empty:
        # no group info, return farm_day-like aggregates with pen_id=NA
        tmp = cow_day.copy()
        tmp["pen_id"] = pd.NA
        moves = tmp[["farm_id", "animal_id", "date", "pen_id"]]
    else:
        moves = moves.copy()
        # Add farm_id if missing (Target v2 fixtures keep it in dm_animals)
        if "farm_id" not in moves.columns and (not animals.empty) and "farm_id" in animals.columns:
            a_cols = [c for c in ["tenant_id", "animal_id", "farm_id"] if c in animals.columns]
            amap = animals[a_cols].drop_duplicates(subset=[c for c in ["tenant_id", "animal_id"] if c in a_cols])
            join_keys = [k for k in ["tenant_id", "animal_id"] if k in moves.columns and k in amap.columns]
            if not join_keys and "animal_id" in moves.columns and "animal_id" in amap.columns:
                join_keys = ["animal_id"]
            if join_keys:
                moves = moves.merge(amap, on=join_keys, how="left")
            else:
                moves["farm_id"] = pd.NA
        # support either move_date or move_datetime
        if "move_datetime" in moves.columns:
            moves["move_date"] = _to_dt(moves["move_datetime"]).dt.floor("D")
        elif "move_date" in moves.columns:
            moves["move_date"] = _to_dt(moves["move_date"]).dt.floor("D")
        else:
            # best-effort: try any column containing 'date'
            cand = [c for c in moves.columns if "date" in c]
            moves["move_date"] = _to_dt(moves[cand[0]]) if cand else pd.NaT
            moves["move_date"] = moves["move_date"].dt.floor("D")

        if "to_pen_id" in moves.columns:
            moves["pen_id"] = moves["to_pen_id"].astype("string")
        elif "pen_id" in moves.columns:
            moves["pen_id"] = moves["pen_id"].astype("string")
        else:
            moves["pen_id"] = pd.NA

        keep = [c for c in ["farm_id", "animal_id", "move_date", "pen_id"] if c in moves.columns]
        moves = moves[keep].dropna(subset=["farm_id", "animal_id", "move_date"], how="any")
        moves = moves.sort_values(["farm_id", "animal_id", "move_date"], kind="mergesort")

    # As-of merge to assign pen_id per cow_day row
    cd = cow_day.copy()
    cd["date_dt"] = _to_dt(cd["date"]).dt.floor("D")
    left = cd.sort_values(["farm_id", "animal_id", "date_dt"], kind="mergesort")
    right = moves.sort_values(["farm_id", "animal_id", "move_date"], kind="mergesort")
    assigned = pd.merge_asof(
        left,
        right,
        left_on="date_dt",
        right_on="move_date",
        by=["farm_id", "animal_id"],
        direction="backward",
        allow_exact_matches=True,
    )
    assigned = assigned.drop(columns=[c for c in ["move_date", "date_dt"] if c in assigned.columns])

    # Aggregations
    grp_cols = ["farm_id", "pen_id", "date"]
    if "pen_id" not in assigned.columns:
        assigned["pen_id"] = pd.NA

    out = assigned.groupby(grp_cols, dropna=False).agg(
        headcount=("animal_id", "nunique"),
        sum_milk_kg=("milk_kg", "sum"),
        avg_milk_kg=("milk_kg", "mean"),
        avg_activity_steps=("activity_steps", "mean"),
        avg_rumination_min=("rumination_min", "mean"),
        avg_body_temp_c=("body_temp_c", "mean"),
        pct_missing_milkings=("is_observed_milkings", lambda s: 1.0 - float(s.mean()) if len(s) else 0.0),
        pct_missing_sensors=("is_observed_sensors", lambda s: 1.0 - float(s.mean()) if len(s) else 0.0),
    )
    out = out.reset_index()
    out = out.sort_values(["farm_id", "pen_id", "date"], kind="mergesort").reset_index(drop=True)
    return out


@dataclass
class TimeSeriesMartsSummary:
    schema: str
    created_at_utc: str
    data_version: str
    marts_run: str
    inputs: Dict[str, Any]
    outputs: Dict[str, str]
    row_counts: Dict[str, int]
    status: str


def build_time_series_marts(
    *,
    artifacts_root: Path,
    data_version: str,
    input_dir: Path,
    marts_run: Optional[str] = None,
) -> Dict[str, Any]:
    """Build time-series marts cow_day and group_day.

    Output layout:
      artifacts/<data_version>/marts/<marts_run>/
        cow_day.parquet, cow_day.csv
        group_day.parquet, group_day.csv
        lineage_manifest.json
        summary.json
        run_manifest.json + checksums.json
    """
    artifacts_root = Path(artifacts_root).resolve()
    input_dir = Path(input_dir).resolve()

    run_id = marts_run or generate_run_id(prefix="marts")
    run_root = artifacts_root / data_version / "marts" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    # Incremental: if previous cow_day exists within this run, extend; else build full.
    existing_cow_day = run_root / "cow_day.pkl"
    start_after = _infer_last_built_date(existing_cow_day)

    cow_day = _build_cow_day(input_dir=input_dir, start_after=start_after)
    if start_after is not None and existing_cow_day.exists():
        try:
            prev = pd.read_pickle(existing_cow_day)
            cow_day = pd.concat([prev, cow_day], ignore_index=True)
            cow_day = cow_day.drop_duplicates(subset=["farm_id", "animal_id", "date"], keep="last")
            cow_day = cow_day.sort_values(["farm_id", "animal_id", "date"], kind="mergesort").reset_index(drop=True)
        except Exception:
            # fall back to fresh build
            cow_day = _build_cow_day(input_dir=input_dir, start_after=None)

    group_day = _build_group_day(cow_day=cow_day, input_dir=input_dir)

    # Save outputs
    outputs: Dict[str, str] = {}
    cow_pkl = run_root / "cow_day.pkl"
    cow_csv = run_root / "cow_day.csv"
    grp_pkl = run_root / "group_day.pkl"
    grp_csv = run_root / "group_day.csv"

    cow_day.to_pickle(cow_pkl)
    cow_day.to_csv(cow_csv, index=False)
    group_day.to_pickle(grp_pkl)
    group_day.to_csv(grp_csv, index=False)

    outputs["cow_day_pkl"] = str(cow_pkl)
    outputs["cow_day_csv"] = str(cow_csv)
    outputs["group_day_pkl"] = str(grp_pkl)
    outputs["group_day_csv"] = str(grp_csv)

    lineage = {
        "schema": "genomeai.lineage_manifest.v1",
        "created_at_utc": _utc_now_iso(),
        "data_version": data_version,
        "marts_run": run_id,
        "inputs": {
            "dm_milkings_daily": str((input_dir / "dm_milkings_daily.csv").resolve()),
            "dm_sensors_daily": str((input_dir / "dm_sensors_daily.csv").resolve()),
            "dm_pen_moves": str((input_dir / "dm_pen_moves.csv").resolve()),
        },
        "cow_day": {
            "keys": ["farm_id", "animal_id", "date"],
            "sources": {
                "milkings": {
                    "dataset": "dm_milkings_daily",
                    "join": "farm_id+animal_id+date",
                    "cols": [
                        "milk_kg",
                        "fat_pct",
                        "protein_pct",
                        "scc_cells_ml",
                        "lactation_id",
                        "dim",
                    ],
                },
                "sensors": {
                    "dataset": "dm_sensors_daily",
                    "join": "farm_id+animal_id+date",
                    "cols": ["activity_steps", "rumination_min", "body_temp_c"],
                },
            },
            "missing_rules": {
                "dense_grid": "daily between min/max observed in either source",
                "flags": ["is_observed_milkings", "is_observed_sensors"],
                "imputation": "forward-fill up to 3 days for select numeric cols into *_ffill3",
            },
        },
        "group_day": {
            "keys": ["farm_id", "pen_id", "date"],
            "pen_assignment": {
                "dataset": "dm_pen_moves",
                "rule": "as-of join by farm_id+animal_id where move_date <= date; pen_id = to_pen_id",
            },
            "aggregations": {
                "headcount": "nunique(animal_id)",
                "sum_milk_kg": "sum(milk_kg)",
                "avg_milk_kg": "mean(milk_kg)",
                "avg_activity_steps": "mean(activity_steps)",
                "avg_rumination_min": "mean(rumination_min)",
                "avg_body_temp_c": "mean(body_temp_c)",
                "pct_missing_milkings": "1-mean(is_observed_milkings)",
                "pct_missing_sensors": "1-mean(is_observed_sensors)",
            },
        },
    }
    lineage_path = run_root / "lineage_manifest.json"
    write_json(lineage_path, lineage)
    outputs["lineage_manifest"] = str(lineage_path)

    summary = TimeSeriesMartsSummary(
        schema="genomeai.marts_timeseries.summary.v1",
        created_at_utc=_utc_now_iso(),
        data_version=data_version,
        marts_run=run_id,
        inputs={"input_dir": str(input_dir)},
        outputs=outputs,
        row_counts={
            "cow_day": int(len(cow_day)),
            "group_day": int(len(group_day)),
        },
        status="OK",
    )
    summary_path = run_root / "summary.json"
    write_json(summary_path, asdict(summary))
    outputs["summary_json"] = str(summary_path)

    # Create a run manifest compatible with the Target run layout
    run_manifest = {
        "schema": "genomeai.run_manifest.v1",
        "tool": "genomeai.marts_timeseries",
        "created_at_utc": _utc_now_iso(),
        "versions": {"data_version": data_version, "marts_run": run_id},
        "inputs": {"input_dir": str(input_dir)},
        "outputs": outputs,
    }
    write_run_manifest(run_root=get_run_root(artifacts_root=artifacts_root, data_version=data_version, run_id=run_id), manifest=run_manifest)
    # checksums for this marts run directory
    write_checksums(run_root=run_root)

    return {"ok": True, **asdict(summary)}

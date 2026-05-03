from __future__ import annotations

"""Drill-down utilities (offline-core).

T10-03 (Drill-down 3.0) is intentionally implemented as small increments.

This module provides:
  - current pen/group assignment for animals at an as-of date
  - KPI breakdown by pen and by animal for a selected KPI id
  - unified animal timeline events (milk / sensors / health / repro)

Important rule: web UI must NOT "compute" KPIs; it calls these helpers.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import yaml


def _parse_date(x: Any) -> Optional[date]:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    if isinstance(x, date) and not isinstance(x, datetime):
        return x
    try:
        return pd.to_datetime(x, errors="coerce").date()
    except Exception:
        return None


def _load_csv(p: Path) -> pd.DataFrame:
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p)


def default_input_dir(*, artifacts_dir: Path, data_version: str, fallback: Path = Path("data/fixtures/target_v2")) -> Path:
    """Resolve a data directory for drill-down facts.

    Priority:
      1) artifacts/<dv>/canonical (if exists)
      2) fallback fixtures (repo)
    """
    cand = artifacts_dir / data_version / "canonical"
    if cand.exists():
        return cand
    return fallback


@dataclass
class PenAssignment:
    tenant_id: str
    animal_id: str
    farm_id: Optional[str]
    site_id: Optional[str]
    pen_id: Optional[str]
    pen_name: Optional[str]


def compute_pen_assignments(*, input_dir: Path, asof_date: date) -> pd.DataFrame:
    """Return current pen assignment for each animal at asof_date.

    Uses dm_animals.current_pen_id as baseline and overrides with last dm_pen_moves move_date<=asof.
    Output columns: tenant_id, animal_id, farm_id, site_id, pen_id, pen_name
    """
    animals = _load_csv(input_dir / "dm_animals.csv")
    pens = _load_csv(input_dir / "dm_pens.csv")
    moves = _load_csv(input_dir / "dm_pen_moves.csv")

    if animals.empty:
        return pd.DataFrame(columns=["tenant_id", "animal_id", "farm_id", "site_id", "pen_id", "pen_name"])

    # Normalize minimal columns
    for c in ["tenant_id", "animal_id", "farm_id", "site_id", "current_pen_id"]:
        if c not in animals.columns:
            animals[c] = pd.NA

    base = animals[["tenant_id", "animal_id", "farm_id", "site_id", "current_pen_id"]].copy()
    base.rename(columns={"current_pen_id": "pen_id"}, inplace=True)

    # Override with last move <= asof
    if not moves.empty:
        for c in ["tenant_id", "animal_id", "to_pen_id", "move_date"]:
            if c not in moves.columns:
                moves[c] = pd.NA
        mv = moves.copy()
        mv["move_date"] = pd.to_datetime(mv["move_date"], errors="coerce").dt.date
        mv = mv.dropna(subset=["tenant_id", "animal_id", "move_date"]).sort_values(["tenant_id", "animal_id", "move_date"])
        mv = mv[mv["move_date"] <= asof_date]
        if not mv.empty:
            last_mv = mv.groupby(["tenant_id", "animal_id"], as_index=False).tail(1)
            last_mv = last_mv[["tenant_id", "animal_id", "to_pen_id"]].rename(columns={"to_pen_id": "pen_id"})
            base = base.drop(columns=["pen_id"]).merge(last_mv, on=["tenant_id", "animal_id"], how="left")

    # Add pen_name
    if not pens.empty:
        for c in ["tenant_id", "pen_id", "pen_name"]:
            if c not in pens.columns:
                pens[c] = pd.NA
        base = base.merge(pens[["tenant_id", "pen_id", "pen_name"]], on=["tenant_id", "pen_id"], how="left")
    else:
        base["pen_name"] = pd.NA

    return base[["tenant_id", "animal_id", "farm_id", "site_id", "pen_id", "pen_name"]].copy()


def _load_kpi_meta(kpi_cfg: Path, kpi_id: str) -> dict:
    try:
        cfg = yaml.safe_load(kpi_cfg.read_text(encoding="utf-8")) or {}
        for k in cfg.get("kpis", []):
            if str(k.get("kpi_id")) == str(kpi_id):
                return k
    except Exception:
        pass
    return {}


def _infer_period_days(kpi_id: str, meta: dict) -> int:
    try:
        if meta and meta.get("period_days"):
            return int(meta.get("period_days"))
    except Exception:
        pass
    # fallback: suffix "_7d" etc
    for suf in ["1d", "7d", "30d", "90d"]:
        if kpi_id.endswith("_" + suf):
            return int(suf[:-1])
    return 7


def kpi_breakdown_by_pen(
    *,
    artifacts_dir: Path,
    data_version: str,
    kpi_id: str,
    asof_date: date,
    input_dir: Optional[Path] = None,
    kpi_cfg: Path = Path("configs/kpi/kpi_v2.yaml"),
) -> pd.DataFrame:
    """Compute KPI breakdown by pen (group).

    Returns columns:
      tenant_id, farm_id, site_id, pen_id, pen_name, kpi_id, asof_date, period_days,
      value, unit, animals_n, sources_json
    """
    in_dir = Path(input_dir) if input_dir else default_input_dir(artifacts_dir=artifacts_dir, data_version=data_version)
    meta = _load_kpi_meta(kpi_cfg, kpi_id)
    period = _infer_period_days(kpi_id, meta)
    unit = str(meta.get("unit") or "")

    assn = compute_pen_assignments(input_dir=in_dir, asof_date=asof_date)
    if assn.empty:
        return pd.DataFrame(
            columns=[
                "tenant_id",
                "farm_id",
                "site_id",
                "pen_id",
                "pen_name",
                "kpi_id",
                "asof_date",
                "period_days",
                "value",
                "unit",
                "animals_n",
                "sources_json",
            ]
        )

    start = asof_date - timedelta(days=period - 1)

    def _mk_out(df: pd.DataFrame, sources: list[str]) -> pd.DataFrame:
        df = df.copy()
        df["kpi_id"] = str(kpi_id)
        df["asof_date"] = asof_date.isoformat()
        df["period_days"] = int(period)
        df["unit"] = unit
        df["sources_json"] = json.dumps(sources, ensure_ascii=False)
        return df

    # --- Milk KPIs ---
    if kpi_id.startswith("milk_total_kg_") or kpi_id == "milk_avg_kg_per_cow_1d" or kpi_id in {"fat_pct_avg_7d", "protein_pct_avg_7d", "scc_avg_7d"}:
        milk = _load_csv(in_dir / "dm_milkings_daily.csv")
        if milk.empty:
            return _mk_out(
                assn[["tenant_id", "farm_id", "site_id", "pen_id", "pen_name"]].drop_duplicates().assign(value=pd.NA, animals_n=pd.NA),
                ["dm_milkings_daily", "dm_animals", "dm_pen_moves"],
            )
        for c in ["tenant_id", "animal_id", "date", "milk_kg", "fat_pct", "protein_pct", "scc_cells_ml"]:
            if c not in milk.columns:
                milk[c] = pd.NA
        milk["date"] = pd.to_datetime(milk["date"], errors="coerce").dt.date
        sub = milk[(milk["date"] >= start) & (milk["date"] <= asof_date)].copy()
        sub = sub.merge(assn, on=["tenant_id", "animal_id"], how="left")

        gcols = ["tenant_id", "farm_id", "site_id", "pen_id", "pen_name"]
        if kpi_id.startswith("milk_total_kg_"):
            sub["milk_kg"] = pd.to_numeric(sub["milk_kg"], errors="coerce")
            agg = sub.groupby(gcols, as_index=False).agg(value=("milk_kg", "sum"), animals_n=("animal_id", "nunique"))
            return _mk_out(agg, ["dm_milkings_daily", "dm_animals", "dm_pen_moves", "dm_pens"])

        if kpi_id == "milk_avg_kg_per_cow_1d":
            # total milk per pen / active cows in pen
            sub["milk_kg"] = pd.to_numeric(sub["milk_kg"], errors="coerce")
            total = sub.groupby(gcols, as_index=False).agg(total_milk=("milk_kg", "sum"))

            animals = _load_csv(in_dir / "dm_animals.csv")
            for c in ["tenant_id", "animal_id", "status"]:
                if c not in animals.columns:
                    animals[c] = pd.NA
            a = animals.merge(assn, on=["tenant_id", "animal_id"], how="left")
            st = a["status"].fillna("active").astype(str).str.lower()
            active = a[st.isin(["active", "lactating", "milking", "in_milk"]) | a["status"].isna()]
            cnt = active.groupby(gcols, as_index=False).agg(animals_n=("animal_id", "nunique"))
            out = total.merge(cnt, on=gcols, how="left")
            out["animals_n"] = pd.to_numeric(out["animals_n"], errors="coerce").fillna(0).astype(int)
            out["value"] = out.apply(lambda r: (float(r["total_milk"]) / float(r["animals_n"])) if r["animals_n"] else float("nan"), axis=1)
            out = out.drop(columns=["total_milk"])
            return _mk_out(out, ["dm_milkings_daily", "dm_animals", "dm_pen_moves", "dm_pens"])

        if kpi_id in {"fat_pct_avg_7d", "protein_pct_avg_7d"}:
            val_col = "fat_pct" if kpi_id == "fat_pct_avg_7d" else "protein_pct"
            sub[val_col] = pd.to_numeric(sub[val_col], errors="coerce")
            sub["milk_kg"] = pd.to_numeric(sub["milk_kg"], errors="coerce")
            # weighted average
            def wavg(g: pd.DataFrame) -> float:
                m = g[[val_col, "milk_kg"]].dropna()
                m = m[m["milk_kg"] > 0]
                if m.empty:
                    return float("nan")
                return float((m[val_col] * m["milk_kg"]).sum() / m["milk_kg"].sum())

            agg = sub.groupby(gcols, as_index=False).apply(lambda g: pd.Series({"value": wavg(g), "animals_n": g["animal_id"].nunique()}))
            return _mk_out(agg, ["dm_milkings_daily", "dm_pen_moves", "dm_pens"])

        if kpi_id == "scc_avg_7d":
            sub["scc_cells_ml"] = pd.to_numeric(sub["scc_cells_ml"], errors="coerce")
            agg = sub.groupby(gcols, as_index=False).agg(value=("scc_cells_ml", "mean"), animals_n=("animal_id", "nunique"))
            return _mk_out(agg, ["dm_milkings_daily", "dm_pen_moves", "dm_pens"])

    # --- Health KPIs ---
    if kpi_id in {"health_events_30d", "mastitis_events_30d", "severe_health_events_30d"}:
        health = _load_csv(in_dir / "dm_health_events.csv")
        if health.empty:
            return _mk_out(
                assn[["tenant_id", "farm_id", "site_id", "pen_id", "pen_name"]].drop_duplicates().assign(value=pd.NA, animals_n=pd.NA),
                ["dm_health_events", "dm_animals", "dm_pen_moves", "dm_pens"],
            )
        for c in ["tenant_id", "animal_id", "event_date", "event_type", "severity"]:
            if c not in health.columns:
                health[c] = pd.NA
        health["event_date"] = pd.to_datetime(health["event_date"], errors="coerce").dt.date
        sub = health[(health["event_date"] >= start) & (health["event_date"] <= asof_date)].copy()
        if kpi_id == "mastitis_events_30d":
            sub = sub[sub["event_type"].astype(str).str.lower().str.contains("mast")]
        if kpi_id == "severe_health_events_30d":
            sub = sub[sub["severity"].astype(str).str.lower().isin(["major", "severe", "critical"])].copy()
        sub = sub.merge(assn, on=["tenant_id", "animal_id"], how="left")
        gcols = ["tenant_id", "farm_id", "site_id", "pen_id", "pen_name"]
        agg = sub.groupby(gcols, as_index=False).agg(value=("event_date", "count"), animals_n=("animal_id", "nunique"))
        return _mk_out(agg, ["dm_health_events", "dm_animals", "dm_pen_moves", "dm_pens"])

    # --- Sensors KPIs ---
    if kpi_id in {"activity_avg_7d", "rumination_avg_7d", "temperature_avg_7d"}:
        sensors = _load_csv(in_dir / "dm_sensors_daily.csv")
        if sensors.empty:
            return _mk_out(
                assn[["tenant_id", "farm_id", "site_id", "pen_id", "pen_name"]].drop_duplicates().assign(value=pd.NA, animals_n=pd.NA),
                ["dm_sensors_daily", "dm_animals", "dm_pen_moves", "dm_pens"],
            )
        for c in ["tenant_id", "animal_id", "date", "activity_count", "rumination_min", "temperature_c"]:
            if c not in sensors.columns:
                sensors[c] = pd.NA
        sensors["date"] = pd.to_datetime(sensors["date"], errors="coerce").dt.date
        sub = sensors[(sensors["date"] >= start) & (sensors["date"] <= asof_date)].copy()
        sub = sub.merge(assn, on=["tenant_id", "animal_id"], how="left")
        gcols = ["tenant_id", "farm_id", "site_id", "pen_id", "pen_name"]
        val_col = "activity_count" if kpi_id == "activity_avg_7d" else "rumination_min" if kpi_id == "rumination_avg_7d" else "temperature_c"
        sub[val_col] = pd.to_numeric(sub[val_col], errors="coerce")
        agg = sub.groupby(gcols, as_index=False).agg(value=(val_col, "mean"), animals_n=("animal_id", "nunique"))
        return _mk_out(agg, ["dm_sensors_daily", "dm_animals", "dm_pen_moves", "dm_pens"])

    # Unknown KPI -> empty
    return pd.DataFrame(
        columns=[
            "tenant_id",
            "farm_id",
            "site_id",
            "pen_id",
            "pen_name",
            "kpi_id",
            "asof_date",
            "period_days",
            "value",
            "unit",
            "animals_n",
            "sources_json",
        ]
    )


def kpi_breakdown_by_animal(
    *,
    artifacts_dir: Path,
    data_version: str,
    kpi_id: str,
    asof_date: date,
    input_dir: Optional[Path] = None,
    kpi_cfg: Path = Path("configs/kpi/kpi_v2.yaml"),
    pen_id: Optional[str] = None,
) -> pd.DataFrame:
    """Compute KPI breakdown by animal. Optionally filter to a pen_id."""
    in_dir = Path(input_dir) if input_dir else default_input_dir(artifacts_dir=artifacts_dir, data_version=data_version)
    meta = _load_kpi_meta(kpi_cfg, kpi_id)
    period = _infer_period_days(kpi_id, meta)
    unit = str(meta.get("unit") or "")

    assn = compute_pen_assignments(input_dir=in_dir, asof_date=asof_date)
    if pen_id:
        assn = assn[assn["pen_id"].astype(str) == str(pen_id)].copy()

    start = asof_date - timedelta(days=period - 1)

    def _mk_out(df: pd.DataFrame, sources: list[str]) -> pd.DataFrame:
        df = df.copy()
        df["kpi_id"] = str(kpi_id)
        df["asof_date"] = asof_date.isoformat()
        df["period_days"] = int(period)
        df["unit"] = unit
        df["sources_json"] = json.dumps(sources, ensure_ascii=False)
        return df

    gcols = ["tenant_id", "animal_id"]

    if kpi_id.startswith("milk_total_kg_"):
        milk = _load_csv(in_dir / "dm_milkings_daily.csv")
        if milk.empty:
            return pd.DataFrame(columns=["tenant_id", "animal_id", "kpi_id", "asof_date", "period_days", "value", "unit", "pen_id", "pen_name", "sources_json"])
        for c in ["tenant_id", "animal_id", "date", "milk_kg"]:
            if c not in milk.columns:
                milk[c] = pd.NA
        milk["date"] = pd.to_datetime(milk["date"], errors="coerce").dt.date
        sub = milk[(milk["date"] >= start) & (milk["date"] <= asof_date)].copy()
        sub["milk_kg"] = pd.to_numeric(sub["milk_kg"], errors="coerce")
        sub = sub.merge(assn[["tenant_id", "animal_id", "pen_id", "pen_name"]], on=["tenant_id", "animal_id"], how="left")
        agg = sub.groupby(gcols + ["pen_id", "pen_name"], as_index=False).agg(value=("milk_kg", "sum"))
        return _mk_out(agg, ["dm_milkings_daily", "dm_pen_moves", "dm_pens"])

    if kpi_id in {"health_events_30d", "mastitis_events_30d", "severe_health_events_30d"}:
        health = _load_csv(in_dir / "dm_health_events.csv")
        if health.empty:
            return pd.DataFrame(columns=["tenant_id", "animal_id", "kpi_id", "asof_date", "period_days", "value", "unit", "pen_id", "pen_name", "sources_json"])
        for c in ["tenant_id", "animal_id", "event_date", "event_type", "severity"]:
            if c not in health.columns:
                health[c] = pd.NA
        health["event_date"] = pd.to_datetime(health["event_date"], errors="coerce").dt.date
        sub = health[(health["event_date"] >= start) & (health["event_date"] <= asof_date)].copy()
        if kpi_id == "mastitis_events_30d":
            sub = sub[sub["event_type"].astype(str).str.lower().str.contains("mast")]
        if kpi_id == "severe_health_events_30d":
            sub = sub[sub["severity"].astype(str).str.lower().isin(["major", "severe", "critical"])].copy()
        sub = sub.merge(assn[["tenant_id", "animal_id", "pen_id", "pen_name"]], on=["tenant_id", "animal_id"], how="left")
        agg = sub.groupby(gcols + ["pen_id", "pen_name"], as_index=False).agg(value=("event_date", "count"))
        return _mk_out(agg, ["dm_health_events", "dm_pen_moves", "dm_pens"])

    if kpi_id in {"activity_avg_7d", "rumination_avg_7d", "temperature_avg_7d"}:
        sensors = _load_csv(in_dir / "dm_sensors_daily.csv")
        if sensors.empty:
            return pd.DataFrame(columns=["tenant_id", "animal_id", "kpi_id", "asof_date", "period_days", "value", "unit", "pen_id", "pen_name", "sources_json"])
        for c in ["tenant_id", "animal_id", "date", "activity_count", "rumination_min", "temperature_c"]:
            if c not in sensors.columns:
                sensors[c] = pd.NA
        sensors["date"] = pd.to_datetime(sensors["date"], errors="coerce").dt.date
        sub = sensors[(sensors["date"] >= start) & (sensors["date"] <= asof_date)].copy()
        val_col = "activity_count" if kpi_id == "activity_avg_7d" else "rumination_min" if kpi_id == "rumination_avg_7d" else "temperature_c"
        sub[val_col] = pd.to_numeric(sub[val_col], errors="coerce")
        sub = sub.merge(assn[["tenant_id", "animal_id", "pen_id", "pen_name"]], on=["tenant_id", "animal_id"], how="left")
        agg = sub.groupby(gcols + ["pen_id", "pen_name"], as_index=False).agg(value=(val_col, "mean"))
        return _mk_out(agg, ["dm_sensors_daily", "dm_pen_moves", "dm_pens"])

    return pd.DataFrame(columns=["tenant_id", "animal_id", "kpi_id", "asof_date", "period_days", "value", "unit", "pen_id", "pen_name", "sources_json"])


def build_animal_timeline(
    *,
    artifacts_dir: Path,
    data_version: str,
    animal_id: str,
    asof_date: date,
    days_back: int = 60,
    input_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """Build unified timeline for one animal.

    Output columns:
      date, category, event_type, details, value_num, unit, source_table
    """
    in_dir = Path(input_dir) if input_dir else default_input_dir(artifacts_dir=artifacts_dir, data_version=data_version)
    start = asof_date - timedelta(days=int(days_back) - 1)

    rows: list[dict[str, Any]] = []

    # Milk
    milk = _load_csv(in_dir / "dm_milkings_daily.csv")
    if not milk.empty:
        for c in ["tenant_id", "animal_id", "date", "milk_kg", "fat_pct", "protein_pct", "scc_cells_ml", "lactation_id"]:
            if c not in milk.columns:
                milk[c] = pd.NA
        milk["date"] = pd.to_datetime(milk["date"], errors="coerce").dt.date
        sub = milk[(milk["animal_id"].astype(str) == str(animal_id)) & (milk["date"] >= start) & (milk["date"] <= asof_date)].copy()
        for _, r in sub.iterrows():
            rows.append(
                {
                    "date": r.get("date"),
                    "category": "milk",
                    "event_type": "milking_daily",
                    "details": f"milk_kg={r.get('milk_kg')} fat={r.get('fat_pct')} protein={r.get('protein_pct')} scc={r.get('scc_cells_ml')}",
                    "value_num": r.get("milk_kg"),
                    "unit": "kg",
                    "source_table": "dm_milkings_daily",
                }
            )

    # Sensors
    sensors = _load_csv(in_dir / "dm_sensors_daily.csv")
    if not sensors.empty:
        for c in ["animal_id", "date", "activity_count", "rumination_min", "temperature_c"]:
            if c not in sensors.columns:
                sensors[c] = pd.NA
        sensors["date"] = pd.to_datetime(sensors["date"], errors="coerce").dt.date
        sub = sensors[(sensors["animal_id"].astype(str) == str(animal_id)) & (sensors["date"] >= start) & (sensors["date"] <= asof_date)].copy()
        for _, r in sub.iterrows():
            rows.append(
                {
                    "date": r.get("date"),
                    "category": "sensors",
                    "event_type": "sensors_daily",
                    "details": f"activity={r.get('activity_count')} rumination={r.get('rumination_min')} temp={r.get('temperature_c')}",
                    "value_num": r.get("activity_count"),
                    "unit": "count",
                    "source_table": "dm_sensors_daily",
                }
            )

    # Health
    health = _load_csv(in_dir / "dm_health_events.csv")
    if not health.empty:
        for c in ["animal_id", "event_date", "event_type", "severity"]:
            if c not in health.columns:
                health[c] = pd.NA
        health["event_date"] = pd.to_datetime(health["event_date"], errors="coerce").dt.date
        sub = health[(health["animal_id"].astype(str) == str(animal_id)) & (health["event_date"] >= start) & (health["event_date"] <= asof_date)].copy()
        for _, r in sub.iterrows():
            rows.append(
                {
                    "date": r.get("event_date"),
                    "category": "health",
                    "event_type": str(r.get("event_type") or "health_event"),
                    "details": f"severity={r.get('severity')}",
                    "value_num": pd.NA,
                    "unit": "",
                    "source_table": "dm_health_events",
                }
            )

    # Repro
    repro = _load_csv(in_dir / "dm_repro_events.csv")
    if not repro.empty:
        for c in ["animal_id", "event_date", "event_type", "result"]:
            if c not in repro.columns:
                repro[c] = pd.NA
        repro["event_date"] = pd.to_datetime(repro["event_date"], errors="coerce").dt.date
        sub = repro[(repro["animal_id"].astype(str) == str(animal_id)) & (repro["event_date"] >= start) & (repro["event_date"] <= asof_date)].copy()
        for _, r in sub.iterrows():
            rows.append(
                {
                    "date": r.get("event_date"),
                    "category": "repro",
                    "event_type": str(r.get("event_type") or "repro_event"),
                    "details": f"result={r.get('result')}",
                    "value_num": pd.NA,
                    "unit": "",
                    "source_table": "dm_repro_events",
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["date", "category", "event_type", "details", "value_num", "unit", "source_table"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df = df.dropna(subset=["date"]).sort_values("date", ascending=False)
    return df

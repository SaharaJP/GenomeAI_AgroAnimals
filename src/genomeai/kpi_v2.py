from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml

from .versioning import generate_run_id, get_run_root, write_run_manifest, write_checksums


@dataclass(frozen=True)
class KPIResult:
    tenant_id: str
    farm_id: str
    asof_date: str  # YYYY-MM-DD
    kpi_id: str
    value: float
    unit: str
    period_days: int
    currency: Optional[str]
    sources: str  # json list[str]


def _parse_date(s: Any) -> Optional[date]:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    try:
        return pd.to_datetime(s).date()
    except Exception:
        return None


def _load_csv(input_dir: Path, name: str) -> pd.DataFrame:
    p = input_dir / name
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p)


def _ensure_cols(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    return df


def _join_animals_farm(df: pd.DataFrame, animals: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "farm_id" in df.columns:
        return df
    if animals.empty:
        df["farm_id"] = pd.NA
        return df
    return df.merge(animals[["tenant_id", "animal_id", "farm_id"]], on=["tenant_id", "animal_id"], how="left")


def _filter_period(df: pd.DataFrame, date_col: str, asof: date, period_days: int) -> pd.DataFrame:
    if df.empty:
        return df
    d = pd.to_datetime(df[date_col], errors="coerce").dt.date
    start = asof - timedelta(days=period_days - 1)
    mask = (d >= start) & (d <= asof)
    return df.loc[mask].copy()


def _weighted_avg(df: pd.DataFrame, value_col: str, weight_col: str) -> float:
    if df.empty:
        return float("nan")
    v = pd.to_numeric(df[value_col], errors="coerce")
    w = pd.to_numeric(df[weight_col], errors="coerce")
    m = (~v.isna()) & (~w.isna()) & (w > 0)
    if not m.any():
        return float("nan")
    return float((v[m] * w[m]).sum() / w[m].sum())


def _safe_mean(df: pd.DataFrame, col: str) -> float:
    if df.empty or col not in df.columns:
        return float("nan")
    v = pd.to_numeric(df[col], errors="coerce")
    if v.dropna().empty:
        return float("nan")
    return float(v.mean())


def compute_kpis(
    *,
    input_dir: Path,
    asof_date: date,
    fx_eur_rub: float,
    currency: str = "RUB",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Compute director-level KPIs (farm-level). Returns (kpi_long, kpi_wide)."""
    # Load required tables (Target v2 fixtures or future canonical exports)
    animals = _load_csv(input_dir, "dm_animals.csv")
    milk = _load_csv(input_dir, "dm_milkings_daily.csv")
    sensors = _load_csv(input_dir, "dm_sensors_daily.csv")
    health = _load_csv(input_dir, "dm_health_events.csv")
    repro = _load_csv(input_dir, "dm_repro_events.csv")
    lact = _load_csv(input_dir, "dm_lactations.csv")
    feed_del = _load_csv(input_dir, "dm_feed_deliveries.csv")
    feed_rat = _load_csv(input_dir, "dm_feed_rations.csv")
    econ = _load_csv(input_dir, "dm_economics_daily.csv")
    alerts = _load_csv(input_dir, "dm_alerts.csv")
    decisions = _load_csv(input_dir, "dm_decisions.csv")

    # Normalize minimal columns
    if not animals.empty:
        animals = _ensure_cols(animals, ["tenant_id", "animal_id", "farm_id", "status"])
    for df, cols in [
        (milk, ["tenant_id","animal_id","date","milk_kg","fat_pct","protein_pct","scc_cells_ml"]),
        (sensors, ["tenant_id","animal_id","date","activity_count","rumination_min","temperature_c"]),
        (health, ["tenant_id","animal_id","event_date","event_type","severity"]),
        (repro, ["tenant_id","animal_id","event_date","event_type","result"]),
        (lact, ["tenant_id","animal_id","calving_date"]),
        (feed_del, ["tenant_id","ration_id","pen_id","delivery_date","feed_kg_as_fed"]),
        (feed_rat, ["tenant_id","ration_id","dm_pct"]),
        (econ, ["tenant_id","farm_id","date","milk_price_per_kg","feed_cost_per_kg_dm","other_cost_eur"]),
        (alerts, ["tenant_id","farm_id","status","created_at"]),
        (decisions, ["tenant_id","farm_id","decision_date","decision"]),
    ]:
        if not df.empty:
            df = _ensure_cols(df, cols)

    # Add farm_id where possible
    milk = _join_animals_farm(milk, animals)
    sensors = _join_animals_farm(sensors, animals)
    health = _join_animals_farm(health, animals)
    repro = _join_animals_farm(repro, animals)
    lact = _join_animals_farm(lact, animals)

    # Derive list of (tenant_id, farm_id) to compute
    farms = []
    if not animals.empty:
        farms = animals[["tenant_id","farm_id"]].dropna().drop_duplicates().values.tolist()
    elif not econ.empty:
        farms = econ[["tenant_id","farm_id"]].dropna().drop_duplicates().values.tolist()
    else:
        farms = [["default","UNKNOWN"]]

    rows: List[KPIResult] = []

    def add(tenant_id: str, farm_id: str, kpi_id: str, value: float, unit: str, period_days: int, sources: List[str], currency_opt: Optional[str]=None):
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return
        rows.append(KPIResult(
            tenant_id=tenant_id,
            farm_id=farm_id,
            asof_date=asof_date.isoformat(),
            kpi_id=kpi_id,
            value=float(value),
            unit=unit,
            period_days=int(period_days),
            currency=currency_opt,
            sources=json.dumps(sources, ensure_ascii=False),
        ))

    # Active cows per farm (for per-cow KPIs)
    active = animals.copy()
    if not active.empty:
        active = active[active["status"].fillna("active").astype(str).str.lower().isin(["active","lactating","milking","in_milk"]) | active["status"].isna()]
        active_counts = active.groupby(["tenant_id","farm_id"])["animal_id"].nunique().to_dict()
    else:
        active_counts = {}

    for tenant_id, farm_id in farms:
        # Milk KPIs
        mf = milk[(milk["tenant_id"]==tenant_id) & (milk["farm_id"]==farm_id)] if not milk.empty else pd.DataFrame()
        for d in [1,7,30]:
            mper = _filter_period(mf, "date", asof_date, d)
            total = pd.to_numeric(mper["milk_kg"], errors="coerce").sum() if not mper.empty else 0.0
            add(tenant_id, farm_id, f"milk_total_kg_{d}d", total, "kg", d, ["dm_milkings_daily","dm_animals"])

        m1 = _filter_period(mf, "date", asof_date, 1)
        total1 = pd.to_numeric(m1["milk_kg"], errors="coerce").sum() if not m1.empty else 0.0
        cows = active_counts.get((tenant_id, farm_id), 0) or (mf["animal_id"].nunique() if not mf.empty else 0)
        avg_per_cow = (total1 / cows) if cows else float("nan")
        add(tenant_id, farm_id, "milk_avg_kg_per_cow_1d", avg_per_cow, "kg/cow/day", 1, ["dm_milkings_daily","dm_animals"])

        m7 = _filter_period(mf, "date", asof_date, 7)
        add(tenant_id, farm_id, "fat_pct_avg_7d", _weighted_avg(m7, "fat_pct", "milk_kg"), "%", 7, ["dm_milkings_daily"])
        add(tenant_id, farm_id, "protein_pct_avg_7d", _weighted_avg(m7, "protein_pct", "milk_kg"), "%", 7, ["dm_milkings_daily"])
        add(tenant_id, farm_id, "scc_avg_7d", _safe_mean(m7, "scc_cells_ml"), "cells/ml", 7, ["dm_milkings_daily"])

        # Health KPIs
        hf = health[(health["tenant_id"]==tenant_id) & (health["farm_id"]==farm_id)] if not health.empty else pd.DataFrame()
        h30 = _filter_period(hf, "event_date", asof_date, 30)
        add(tenant_id, farm_id, "health_events_30d", float(len(h30)), "count", 30, ["dm_health_events","dm_animals"])
        mast = h30[h30["event_type"].astype(str).str.lower().str.contains("mast")] if not h30.empty else pd.DataFrame()
        add(tenant_id, farm_id, "mastitis_events_30d", float(len(mast)), "count", 30, ["dm_health_events"])
        sev = h30[h30["severity"].astype(str).str.lower().isin(["major","severe","critical"])] if not h30.empty else pd.DataFrame()
        add(tenant_id, farm_id, "severe_health_events_30d", float(len(sev)), "count", 30, ["dm_health_events"])

        # Sensors KPIs
        sf = sensors[(sensors["tenant_id"]==tenant_id) & (sensors["farm_id"]==farm_id)] if not sensors.empty else pd.DataFrame()
        s7 = _filter_period(sf, "date", asof_date, 7)
        add(tenant_id, farm_id, "activity_avg_7d", _safe_mean(s7, "activity_count"), "count/day", 7, ["dm_sensors_daily","dm_animals"])
        add(tenant_id, farm_id, "rumination_avg_7d", _safe_mean(s7, "rumination_min"), "min/day", 7, ["dm_sensors_daily"])
        add(tenant_id, farm_id, "temperature_avg_7d", _safe_mean(s7, "temperature_c"), "C", 7, ["dm_sensors_daily"])

        # Repro KPIs
        rf = repro[(repro["tenant_id"]==tenant_id) & (repro["farm_id"]==farm_id)] if not repro.empty else pd.DataFrame()
        r30 = _filter_period(rf, "event_date", asof_date, 30)
        insems = r30[r30["event_type"].astype(str).str.lower().str.contains("insemin")] if not r30.empty else pd.DataFrame()
        add(tenant_id, farm_id, "inseminations_30d", float(len(insems)), "count", 30, ["dm_repro_events","dm_animals"])
        r90 = _filter_period(rf, "event_date", asof_date, 90)
        preg = r90[r90["result"].astype(str).str.lower().isin(["pregnant","positive","yes"])] if not r90.empty else pd.DataFrame()
        add(tenant_id, farm_id, "pregnancy_positive_90d", float(len(preg)), "count", 90, ["dm_repro_events"])
        lf = lact[(lact["tenant_id"]==tenant_id) & (lact["farm_id"]==farm_id)] if not lact.empty else pd.DataFrame()
        l90 = _filter_period(lf, "calving_date", asof_date, 90)
        add(tenant_id, farm_id, "calvings_90d", float(len(l90)), "count", 90, ["dm_lactations","dm_animals"])

        # Feeding KPIs (farm-level: sum deliveries; pen-to-farm mapping not in fixtures, so farm=UNKNOWN unless econ/animals present)
        fd7 = _filter_period(feed_del, "delivery_date", asof_date, 7) if not feed_del.empty else pd.DataFrame()
        # deliveries not linked to farm in v2 fixture; treat as farm-wide for tenant if farm_id matches exists else include all
        if not fd7.empty:
            fd7_t = fd7[fd7["tenant_id"]==tenant_id]
        else:
            fd7_t = pd.DataFrame()
        feed_asfed = pd.to_numeric(fd7_t["feed_kg_as_fed"], errors="coerce").sum() if not fd7_t.empty else 0.0
        add(tenant_id, farm_id, "feed_as_fed_kg_7d", feed_asfed, "kg", 7, ["dm_feed_deliveries"])

        if not fd7_t.empty and not feed_rat.empty:
            rat = feed_rat[feed_rat["tenant_id"]==tenant_id][["ration_id","dm_pct"]].drop_duplicates()
            tmp = fd7_t.merge(rat, on="ration_id", how="left")
            dm_pct = pd.to_numeric(tmp["dm_pct"], errors="coerce")/100.0
            dm_kg = (pd.to_numeric(tmp["feed_kg_as_fed"], errors="coerce") * dm_pct).sum()
        else:
            dm_kg = 0.0
        add(tenant_id, farm_id, "feed_dm_kg_7d", dm_kg, "kg DM", 7, ["dm_feed_deliveries","dm_feed_rations"])
        cows = active_counts.get((tenant_id, farm_id), 0) or 0
        feed_dm_per_cow = (dm_kg / cows / 7.0) if cows else float("nan")
        add(tenant_id, farm_id, "feed_dm_kg_per_cow_7d", feed_dm_per_cow, "kg DM/cow/day", 7, ["dm_feed_deliveries","dm_feed_rations","dm_animals"])

        # Economics KPIs (RUB): use econ daily price/cost in EUR if provided; apply fx.
        ef = econ[(econ["tenant_id"]==tenant_id) & (econ["farm_id"]==farm_id)] if not econ.empty else pd.DataFrame()
        e7 = _filter_period(ef, "date", asof_date, 7)
        milk_price = pd.to_numeric(e7["milk_price_per_kg"], errors="coerce").mean() if not e7.empty else float("nan")
        feed_cost_per = pd.to_numeric(e7["feed_cost_per_kg_dm"], errors="coerce").mean() if not e7.empty else float("nan")
        other_cost_eur = pd.to_numeric(e7["other_cost_eur"], errors="coerce").sum() if not e7.empty else 0.0

        # Revenue based on milk_kg_7d * milk_price_per_kg
        milk7_total = pd.to_numeric(m7["milk_kg"], errors="coerce").sum() if not m7.empty else 0.0
        revenue_eur = milk7_total * (milk_price if not pd.isna(milk_price) else 0.0)
        revenue_rub = revenue_eur * fx_eur_rub
        add(tenant_id, farm_id, "milk_revenue_rub_7d", revenue_rub, "RUB", 7, ["dm_milkings_daily","dm_economics_daily","fx_rates"], currency_opt=currency)

        feed_cost_eur = dm_kg * (feed_cost_per if not pd.isna(feed_cost_per) else 0.0)
        feed_cost_rub = feed_cost_eur * fx_eur_rub
        add(tenant_id, farm_id, "feed_cost_rub_7d", feed_cost_rub, "RUB", 7, ["dm_feed_deliveries","dm_feed_rations","dm_economics_daily","fx_rates"], currency_opt=currency)

        other_cost_rub = other_cost_eur * fx_eur_rub
        add(tenant_id, farm_id, "other_cost_rub_7d", other_cost_rub, "RUB", 7, ["dm_economics_daily","fx_rates"], currency_opt=currency)

        margin_rub = revenue_rub - feed_cost_rub - other_cost_rub
        add(tenant_id, farm_id, "margin_rub_7d", margin_rub, "RUB", 7, ["derived"], currency_opt=currency)

        # Alerts KPI
        af = alerts[(alerts["tenant_id"]==tenant_id) & (alerts["farm_id"]==farm_id)] if not alerts.empty else pd.DataFrame()
        open_cnt = float((af["status"].astype(str).str.lower()=="open").sum()) if not af.empty else 0.0
        add(tenant_id, farm_id, "alerts_open_count", open_cnt, "count", 0, ["dm_alerts"])

        # Decisions accept rate 90d
        df = decisions[(decisions["tenant_id"]==tenant_id) & (decisions["farm_id"]==farm_id)] if not decisions.empty else pd.DataFrame()
        if not df.empty:
            df["decision_date"] = pd.to_datetime(df["decision_date"], errors="coerce").dt.date
            start = asof_date - timedelta(days=89)
            d90 = df[(df["decision_date"]>=start) & (df["decision_date"]<=asof_date)]
        else:
            d90 = pd.DataFrame()
        if d90.empty:
            rate = float("nan")
        else:
            acc = (d90["decision"].astype(str).str.lower()=="accept").sum()
            rate = 100.0 * acc / len(d90)
        add(tenant_id, farm_id, "decisions_accept_rate_90d", rate, "%", 90, ["dm_decisions"])

    kpi_long = pd.DataFrame([r.__dict__ for r in rows])
    if kpi_long.empty:
        kpi_wide = pd.DataFrame()
    else:
        kpi_wide = kpi_long.pivot_table(
            index=["tenant_id","farm_id","asof_date"],
            columns="kpi_id",
            values="value",
            aggfunc="first"
        ).reset_index()
    return kpi_long, kpi_wide


def apply_thresholds(*, kpi_long: pd.DataFrame, thresholds_cfg: dict) -> pd.DataFrame:
    """Create alerts based on KPI thresholds. Does NOT block computation."""
    if kpi_long.empty:
        return pd.DataFrame(columns=["tenant_id","farm_id","asof_date","kpi_id","severity","alert_type","message","value","unit"])
    rules = thresholds_cfg.get("thresholds", [])
    out = []
    for r in rules:
        kid = r["kpi_id"]
        sub = kpi_long[kpi_long["kpi_id"]==kid]
        if sub.empty:
            continue
        for _, row in sub.iterrows():
            v = float(row["value"])
            triggered = False
            if "low" in r and v < float(r["low"]):
                triggered = True
            if "high" in r and v > float(r["high"]):
                triggered = True
            if triggered:
                out.append({
                    "tenant_id": row["tenant_id"],
                    "farm_id": row["farm_id"],
                    "asof_date": row["asof_date"],
                    "kpi_id": kid,
                    "severity": r.get("severity","MINOR"),
                    "alert_type": r.get("alert_type","KPI_ALERT"),
                    "message": r.get("message","KPI threshold breached"),
                    "value": v,
                    "unit": row["unit"],
                })
    return pd.DataFrame(out)


def run_kpi(
    *,
    data_version: str,
    asof_date: str,
    artifacts_root: Path,
    input_dir: Path,
    run_id: Optional[str] = None,
    config_kpi: Path = Path("configs/kpi/kpi_v2.yaml"),
    config_thresholds: Path = Path("configs/kpi/kpi_thresholds_v2.yaml"),
) -> dict:
    run_id = run_id or generate_run_id("kpi")
    run_root = get_run_root(artifacts_root=artifacts_root, data_version=data_version, run_id=run_id)
    out_dir = run_root / "kpi"
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg_thr = yaml.safe_load(config_thresholds.read_text(encoding="utf-8")) if config_thresholds.exists() else {"fx_rates":{"EUR_RUB":100.0}, "thresholds":[]}
    fx = float(cfg_thr.get("fx_rates", {}).get("EUR_RUB", 100.0))
    currency = str(cfg_thr.get("currency","RUB"))

    asof = datetime.strptime(asof_date, "%Y-%m-%d").date()
    kpi_long, kpi_wide = compute_kpis(input_dir=input_dir, asof_date=asof, fx_eur_rub=fx, currency=currency)
    alerts = apply_thresholds(kpi_long=kpi_long, thresholds_cfg=cfg_thr)

    # write outputs
    kpi_long.to_csv(out_dir / "kpi_long.csv", index=False)
    kpi_wide.to_csv(out_dir / "kpi_wide.csv", index=False)
    alerts.to_csv(out_dir / "kpi_alerts.csv", index=False)

    summary = {
        "data_version": data_version,
        "run_id": run_id,
        "asof_date": asof_date,
        "currency": currency,
        "kpi_count": int(kpi_long["kpi_id"].nunique()) if not kpi_long.empty else 0,
        "alert_count": int(len(alerts)),
        "inputs": str(input_dir),
        "fx_rates": {"EUR_RUB": fx},
        "blocking_policy": "alerts_only",
    }
    (out_dir / "kpi_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "step": "kpi_v2",
        "data_version": data_version,
        "run_id": run_id,
        "asof_date": asof_date,
        "inputs": {
            "input_dir": str(input_dir),
            "config_kpi": str(config_kpi),
            "config_thresholds": str(config_thresholds),
        },
        "outputs": {
            "kpi_long": str((out_dir / "kpi_long.csv").relative_to(run_root)),
            "kpi_wide": str((out_dir / "kpi_wide.csv").relative_to(run_root)),
            "kpi_alerts": str((out_dir / "kpi_alerts.csv").relative_to(run_root)),
            "kpi_summary": str((out_dir / "kpi_summary.json").relative_to(run_root)),
        },
        "lineage": {},
    }
    write_run_manifest(run_root=run_root, manifest=manifest)
    write_checksums(run_root=run_root, include_subdirs=["kpi"])

    return {
        "data_version": data_version,
        "run_id": run_id,
        "run_root": str(run_root),
        "kpi_dir": str(out_dir),
        "kpi_count": summary["kpi_count"],
        "alert_count": summary["alert_count"],
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="genomeai-kpi")
    p.add_argument("--data-version", required=True)
    p.add_argument("--asof-date", required=True, help="YYYY-MM-DD")
    p.add_argument("--input-dir", default=None, help="Directory with Target v2 CSVs (fixtures or canonical exports)")
    p.add_argument("--artifacts", default="artifacts")
    p.add_argument("--run-id", default=None)
    p.add_argument("--config-kpi", default="configs/kpi/kpi_v2.yaml")
    p.add_argument("--config-thresholds", default="configs/kpi/kpi_thresholds_v2.yaml")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    artifacts_root = Path(args.artifacts)
    input_dir = Path(args.input_dir) if args.input_dir else (artifacts_root / args.data_version / "canonical")
    res = run_kpi(
        data_version=args.data_version,
        asof_date=args.asof_date,
        artifacts_root=artifacts_root,
        input_dir=input_dir,
        run_id=args.run_id,
        config_kpi=Path(args.config_kpi),
        config_thresholds=Path(args.config_thresholds),
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

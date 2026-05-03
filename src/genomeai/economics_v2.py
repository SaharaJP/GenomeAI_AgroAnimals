from __future__ import annotations

"""T11-01: Экономика 2.0 — витрины доходов/расходов и себестоимости (RUB).

Ключевой принцип:
- Web/UI ничего не «считает». Он вызывает offline-core (этот модуль) и читает артефакты.
- Все выходные суммы — в рублях (RUB, ₽).
- Прозрачность формул: в витринах есть formula_json (формулы + подставленные параметры).

Канонические источники (canonical dir):
- dm_milkings_daily: tenant_id, animal_id, date, milk_kg
- dm_animals: tenant_id, animal_id, farm_id, site_id, current_pen_id
- dm_pen_moves (опционально): tenant_id, animal_id, to_pen_id, move_date
- dm_pens + dm_sites: pen_id -> site_id -> farm_id
- dm_feed_deliveries + dm_feed_rations: feed_kg_as_fed * dm_pct -> feed_dm_kg
- dm_economics_daily (опционально): farm_id, date, milk_price_per_kg, feed_cost_per_kg_dm, other_cost_* (вх. валюта)
- dm_prices (опционально): fallback цена молока с указанием currency
- dm_treatments (опционально): начало лечения -> vet cost model
- dm_repro_events (опционально): insemination -> repro cost model

Выходные витрины:
- economics_daily (гранулярность: farm/site/pen x date)
- economics_monthly (гранулярность: farm/site/pen x YYYY-MM)

Версии:
- data_version + economics_run (run_id)

"""

import json
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from .versioning import generate_run_id, write_checksums, write_json, ensure_run_dir, write_run_manifest
from .refdata import RefdataStore, connect_sqlite

DEFAULT_CFG_PATH = Path("configs/economics/economics_v2.yaml")


def _utc_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _resolve_canonical_dir(artifacts_root: Path, data_version: str, input_dir: Optional[Path] = None) -> Path:
    if input_dir is not None:
        return Path(input_dir)
    p1 = Path(artifacts_root) / data_version / "canonical"
    p2 = Path(artifacts_root) / "canonical" / data_version
    if p2.exists():
        return p2
    return p1


def _read_table(canonical_dir: Path, dataset: str) -> pd.DataFrame:
    pq = canonical_dir / f"{dataset}.parquet"
    if pq.exists():
        try:
            return pd.read_parquet(pq)
        except Exception:
            pass
    csv = canonical_dir / f"{dataset}.csv"
    if csv.exists():
        return pd.read_csv(csv)
    return pd.DataFrame()


def _load_cfg(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore

        obj = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
        return obj or {}
    except Exception:
        return {}


def _fx(cfg: Dict[str, Any], ccy: str) -> float:
    fx = (cfg or {}).get("fx_rates", {}) or {}
    c = (ccy or "RUB").upper().strip()
    try:
        return float(fx.get(c, 1.0))
    except Exception:
        return 1.0


def _to_rub(cfg: Dict[str, Any], value: float, currency: str) -> float:
    return float(value) * _fx(cfg, currency)


def _parse_date_col(df: pd.DataFrame, col: str) -> pd.Series:
    if df.empty or col not in df.columns:
        return pd.Series(dtype="datetime64[ns]")
    return pd.to_datetime(df[col], errors="coerce").dt.normalize()


def _float_series(values: Any, *, index: pd.Index | None = None) -> pd.Series:
    """Return a float64 Series aligned to index for dtype-safe numeric assignments."""
    if isinstance(values, pd.Series):
        ser = pd.to_numeric(values, errors="coerce")
        if index is not None:
            ser = ser.reindex(index)
        return ser.astype("float64", copy=False)
    if index is None:
        return pd.Series(pd.to_numeric(values, errors="coerce"), dtype="float64")
    if values is None:
        return pd.Series(index=index, dtype="float64")
    if isinstance(values, Iterable) and not isinstance(values, (str, bytes, bytearray)):
        return pd.Series(pd.to_numeric(list(values), errors="coerce"), index=index, dtype="float64")
    return pd.Series(pd.to_numeric([values] * len(index), errors="coerce"), index=index, dtype="float64")


def _assign_float_where(df: pd.DataFrame, *, column: str, mask: pd.Series, values: Any) -> None:
    """Assign numeric values without triggering pandas incompatible-dtype warnings."""
    aligned_mask = pd.Series(mask, index=df.index).fillna(False).astype(bool)
    base = _float_series(df.get(column), index=df.index)
    override = _float_series(values, index=df.index)
    df[column] = base.where(~aligned_mask, override)


def _normalize_concat_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Drop per-frame all-NA columns before concat to preserve legacy dtype inference."""
    if df is None:
        return pd.DataFrame()
    out = df.copy()
    if out.empty:
        return out.iloc[:, 0:0].copy()
    keep = [c for c in out.columns if not out[c].isna().all()]
    if not keep:
        return out.iloc[:, 0:0].copy()
    return out[keep].copy()


def _concat_legacy_compatible(frames: list[pd.DataFrame]) -> pd.DataFrame:
    normalized = [_normalize_concat_frame(df) for df in frames]
    if not normalized:
        return pd.DataFrame()
    return pd.concat(normalized, axis=0, ignore_index=True, sort=False)


def _assign_pen_on_date(
    records: pd.DataFrame,
    animals: pd.DataFrame,
    pen_moves: pd.DataFrame,
) -> pd.DataFrame:
    """Assign pen_id to each record using latest move <= date, fallback to animals.current_pen_id.

    Expected input columns: tenant_id (optional), animal_id, date.
    Returns input columns + pen_id + farm_id (if present in animals).
    """
    out = records.copy()
    if out.empty:
        out["pen_id"] = None
        return out

    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()

    # merge baseline (animal -> current_pen_id, farm_id, site_id)
    if animals.empty:
        a = pd.DataFrame(columns=["tenant_id", "animal_id", "farm_id", "site_id", "current_pen_id"])
    else:
        cols = [c for c in ["tenant_id", "animal_id", "farm_id", "site_id", "current_pen_id"] if c in animals.columns]
        a = animals[cols].copy()
        if "tenant_id" not in a.columns:
            a["tenant_id"] = "default"
    if "tenant_id" not in out.columns:
        out["tenant_id"] = "default"

    out = out.merge(a, on=["tenant_id", "animal_id"], how="left")
    out.rename(columns={"current_pen_id": "pen_id"}, inplace=True)

    if pen_moves.empty:
        return out

    pm = pen_moves.copy()
    for c in ["move_date"]:
        if c in pm.columns:
            pm[c] = pd.to_datetime(pm[c], errors="coerce").dt.normalize()
    # require minimal cols
    need = {"animal_id", "to_pen_id", "move_date"}
    if not need.issubset(set(pm.columns)):
        return out
    if "tenant_id" not in pm.columns:
        pm["tenant_id"] = "default"

    pm = pm.sort_values(["tenant_id", "animal_id", "move_date"]).dropna(subset=["tenant_id", "animal_id", "move_date"])

    out = out.sort_values(["tenant_id", "animal_id", "date"]).reset_index(drop=True)
    pm = pm.rename(columns={"to_pen_id": "pen_id_move"})
    pm = pm[["tenant_id", "animal_id", "move_date", "pen_id_move"]]

    merged = pd.merge_asof(
        out,
        pm,
        left_on="date",
        right_on="move_date",
        by=["tenant_id", "animal_id"],
        direction="backward",
        allow_exact_matches=True,
    )
    merged["pen_id"] = merged["pen_id_move"].fillna(merged["pen_id"])  # override baseline
    return merged.drop(columns=[c for c in ["move_date", "pen_id_move"] if c in merged.columns])


def _build_pen_map(pens: pd.DataFrame, sites: pd.DataFrame) -> pd.DataFrame:
    if pens.empty:
        return pd.DataFrame(columns=["tenant_id", "pen_id", "pen_name", "site_id", "farm_id", "pen_type"])
    p = pens.copy()
    if "tenant_id" not in p.columns:
        p["tenant_id"] = "default"
    for c in ["pen_id", "site_id", "pen_type", "pen_name"]:
        if c not in p.columns:
            p[c] = pd.NA

    if sites.empty:
        s = pd.DataFrame(columns=["tenant_id", "site_id", "farm_id"])
    else:
        s = sites[[c for c in ["tenant_id", "site_id", "farm_id"] if c in sites.columns]].copy()
        if "tenant_id" not in s.columns:
            s["tenant_id"] = "default"

    out = p.merge(s, on=["tenant_id", "site_id"], how="left")
    if "farm_id" not in out.columns:
        out["farm_id"] = pd.NA
    return out[["tenant_id", "pen_id", "pen_name", "site_id", "farm_id", "pen_type"]].copy()


def _build_milk_pen_day(
    *,
    milkings: pd.DataFrame,
    animals: pd.DataFrame,
    pen_moves: pd.DataFrame,
    pen_map: pd.DataFrame,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
) -> pd.DataFrame:
    if milkings.empty:
        return pd.DataFrame(columns=["tenant_id", "farm_id", "site_id", "pen_id", "pen_name", "pen_type", "date", "milk_kg"])

    mcols = [c for c in ["tenant_id", "animal_id", "date", "milk_kg"] if c in milkings.columns]
    m = milkings[mcols].copy()
    if "tenant_id" not in m.columns:
        m["tenant_id"] = "default"
    m["date"] = pd.to_datetime(m["date"], errors="coerce").dt.normalize()
    m = m[(m["date"] >= date_from) & (m["date"] <= date_to)].copy()
    m["milk_kg"] = pd.to_numeric(m.get("milk_kg"), errors="coerce")
    m = m.dropna(subset=["tenant_id", "animal_id", "date", "milk_kg"])

    assigned = _assign_pen_on_date(m, animals, pen_moves)
    assigned = assigned.merge(pen_map, on=["tenant_id", "pen_id"], how="left", suffixes=("", "_pm"))
    # farm_id fallback from animals
    if "farm_id_pm" in assigned.columns:
        assigned["farm_id"] = assigned.get("farm_id").fillna(assigned["farm_id_pm"])
        assigned.drop(columns=["farm_id_pm"], inplace=True)

    out = (
        assigned.groupby(["tenant_id", "farm_id", "site_id", "pen_id", "pen_name", "pen_type", "date"], dropna=False)["milk_kg"]
        .sum()
        .reset_index()
    )
    return out


def _build_feed_pen_day(
    *,
    deliveries: pd.DataFrame,
    rations: pd.DataFrame,
    pen_map: pd.DataFrame,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
) -> pd.DataFrame:
    if deliveries.empty:
        return pd.DataFrame(columns=["tenant_id", "farm_id", "site_id", "pen_id", "pen_name", "pen_type", "date", "feed_dm_kg"])

    d = deliveries.copy()
    if "tenant_id" not in d.columns:
        d["tenant_id"] = "default"
    d["date"] = pd.to_datetime(d.get("delivery_date", d.get("date")), errors="coerce").dt.normalize()
    d = d[(d["date"] >= date_from) & (d["date"] <= date_to)].copy()
    d["feed_kg_as_fed"] = pd.to_numeric(d.get("feed_kg_as_fed"), errors="coerce")
    d = d.dropna(subset=["tenant_id", "pen_id", "ration_id", "date", "feed_kg_as_fed"])

    r = rations.copy() if not rations.empty else pd.DataFrame(columns=["tenant_id", "ration_id", "dm_pct"])
    if "tenant_id" not in r.columns and not r.empty:
        r["tenant_id"] = "default"
    r["dm_pct"] = pd.to_numeric(r.get("dm_pct"), errors="coerce")

    d = d.merge(r[["tenant_id", "ration_id", "dm_pct"]], on=["tenant_id", "ration_id"], how="left")
    d["dm_pct"] = d["dm_pct"].fillna(50.0)
    d["feed_dm_kg"] = d["feed_kg_as_fed"] * (d["dm_pct"] / 100.0)

    d = d.merge(pen_map, on=["tenant_id", "pen_id"], how="left")

    out = (
        d.groupby(["tenant_id", "farm_id", "site_id", "pen_id", "pen_name", "pen_type", "date"], dropna=False)["feed_dm_kg"]
        .sum()
        .reset_index()
    )
    return out


def _build_treatments_pen_day(
    *,
    treatments: pd.DataFrame,
    animals: pd.DataFrame,
    pen_moves: pd.DataFrame,
    pen_map: pd.DataFrame,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
) -> pd.DataFrame:
    if treatments.empty:
        return pd.DataFrame(columns=["tenant_id", "farm_id", "site_id", "pen_id", "date", "treatments_n"])

    t = treatments.copy()
    if "tenant_id" not in t.columns:
        t["tenant_id"] = "default"
    t["date"] = pd.to_datetime(t.get("start_date", t.get("date")), errors="coerce").dt.normalize()
    t = t[(t["date"] >= date_from) & (t["date"] <= date_to)].copy()
    if t.empty:
        return pd.DataFrame(columns=["tenant_id", "farm_id", "site_id", "pen_id", "date", "treatments_n"])

    base = t[[c for c in ["tenant_id", "animal_id", "date"] if c in t.columns]].copy()
    base["treatments_n"] = 1
    assigned = _assign_pen_on_date(base, animals, pen_moves)
    # Merge pen_map safely: animals may already provide farm_id/site_id; prefer explicit mapping from pen_map when present.
    assigned = assigned.merge(pen_map, on=["tenant_id", "pen_id"], how="left", suffixes=("", "_pm"))
    for k in ["farm_id", "site_id", "pen_name", "pen_type"]:
        pmk = f"{k}_pm"
        if pmk not in assigned.columns:
            continue
        if k in assigned.columns:
            assigned[k] = assigned[k].fillna(assigned[pmk])
        else:
            assigned[k] = assigned[pmk]
        assigned.drop(columns=[pmk], inplace=True)

    out = (
        assigned.groupby(["tenant_id", "farm_id", "site_id", "pen_id", "date"], dropna=False)["treatments_n"]
        .sum()
        .reset_index()
    )
    return out


def _build_repro_pen_day(
    *,
    repro_events: pd.DataFrame,
    animals: pd.DataFrame,
    pen_moves: pd.DataFrame,
    pen_map: pd.DataFrame,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
) -> pd.DataFrame:
    if repro_events.empty:
        return pd.DataFrame(columns=["tenant_id", "farm_id", "site_id", "pen_id", "date", "inseminations_n"])

    r = repro_events.copy()
    if "tenant_id" not in r.columns:
        r["tenant_id"] = "default"
    r["date"] = pd.to_datetime(r.get("event_date", r.get("date")), errors="coerce").dt.normalize()
    r = r[(r["date"] >= date_from) & (r["date"] <= date_to)].copy()
    if "event_type" in r.columns:
        r = r[r["event_type"].astype(str).str.lower().isin({"insemination", "ai"})].copy()
    if r.empty:
        return pd.DataFrame(columns=["tenant_id", "farm_id", "site_id", "pen_id", "date", "inseminations_n"])

    base = r[[c for c in ["tenant_id", "animal_id", "date"] if c in r.columns]].copy()
    base["inseminations_n"] = 1
    assigned = _assign_pen_on_date(base, animals, pen_moves)
    assigned = assigned.merge(pen_map, on=["tenant_id", "pen_id"], how="left", suffixes=("", "_pm"))
    for k in ["farm_id", "site_id", "pen_name", "pen_type"]:
        pmk = f"{k}_pm"
        if pmk not in assigned.columns:
            continue
        if k in assigned.columns:
            assigned[k] = assigned[k].fillna(assigned[pmk])
        else:
            assigned[k] = assigned[pmk]
        assigned.drop(columns=[pmk], inplace=True)

    out = (
        assigned.groupby(["tenant_id", "farm_id", "site_id", "pen_id", "date"], dropna=False)["inseminations_n"]
        .sum()
        .reset_index()
    )
    return out




def _build_cull_pen_day(
    *,
    cull_events: pd.DataFrame,
    animals: pd.DataFrame,
    pen_moves: pd.DataFrame,
    pen_map: pd.DataFrame,
    cfg: Dict[str, Any],
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
) -> pd.DataFrame:
    """Build pen-day cull/realization aggregates.

    Canonical (best-effort) supported columns:
    - tenant_id (optional)
    - animal_id
    - event_date/date
    - revenue_rub or revenue + revenue_ccy
    - cost_rub or cost + cost_ccy

    If revenue/cost missing — uses cfg.cost_models.cull.{revenue_per_head_rub,cost_per_head_rub}.
    """

    if cull_events.empty:
        return pd.DataFrame(
            columns=[
                "tenant_id",
                "farm_id",
                "site_id",
                "pen_id",
                "date",
                "cull_events_n",
                "revenue_cull_rub",
                "cost_cull_rub",
            ]
        )

    ce = cull_events.copy()
    if "tenant_id" not in ce.columns:
        ce["tenant_id"] = "default"
    ce["date"] = pd.to_datetime(ce.get("event_date", ce.get("date")), errors="coerce").dt.normalize()
    ce = ce[(ce["date"] >= date_from) & (ce["date"] <= date_to)].copy()
    ce = ce.dropna(subset=["tenant_id", "animal_id", "date"]) if "animal_id" in ce.columns else pd.DataFrame()
    if ce.empty:
        return pd.DataFrame(
            columns=[
                "tenant_id",
                "farm_id",
                "site_id",
                "pen_id",
                "date",
                "cull_events_n",
                "revenue_cull_rub",
                "cost_cull_rub",
            ]
        )

    cm = (cfg or {}).get("cost_models", {}) or {}
    cull_cfg = cm.get("cull", {}) or {}
    def_rev = float(cull_cfg.get("revenue_per_head_rub", 0.0))
    def_cost = float(cull_cfg.get("cost_per_head_rub", 0.0))

    ce["cull_events_n"] = 1

    # revenue
    if "revenue_rub" in ce.columns:
        ce["revenue_cull_rub"] = pd.to_numeric(ce["revenue_rub"], errors="coerce")
    elif "revenue" in ce.columns:
        ccy = ce.get("revenue_ccy", "RUB").astype(str)
        ce["revenue_cull_rub"] = pd.to_numeric(ce["revenue"], errors="coerce") * ccy.map(lambda c: _fx(cfg, str(c)))
    else:
        ce["revenue_cull_rub"] = def_rev

    # cost
    if "cost_rub" in ce.columns:
        ce["cost_cull_rub"] = pd.to_numeric(ce["cost_rub"], errors="coerce")
    elif "cost" in ce.columns:
        ccy2 = ce.get("cost_ccy", "RUB").astype(str)
        ce["cost_cull_rub"] = pd.to_numeric(ce["cost"], errors="coerce") * ccy2.map(lambda c: _fx(cfg, str(c)))
    else:
        ce["cost_cull_rub"] = def_cost

    ce["revenue_cull_rub"] = pd.to_numeric(ce["revenue_cull_rub"], errors="coerce").fillna(def_rev)
    ce["cost_cull_rub"] = pd.to_numeric(ce["cost_cull_rub"], errors="coerce").fillna(def_cost)

    base = ce[["tenant_id", "animal_id", "date", "cull_events_n", "revenue_cull_rub", "cost_cull_rub"]].copy()

    assigned = _assign_pen_on_date(base[["tenant_id", "animal_id", "date"]], animals, pen_moves)
    assigned = assigned[[c for c in ["tenant_id", "animal_id", "date", "pen_id", "farm_id", "site_id"] if c in assigned.columns]].copy()
    base = base.merge(assigned, on=["tenant_id", "animal_id", "date"], how="left")

    # Fill farm/site from pen_map if needed
    pm = pen_map[["tenant_id", "pen_id", "farm_id", "site_id"]].copy() if not pen_map.empty else pd.DataFrame(columns=["tenant_id", "pen_id", "farm_id", "site_id"])
    base = base.merge(pm, on=["tenant_id", "pen_id"], how="left", suffixes=("", "_pm"))
    if "farm_id_pm" in base.columns:
        base["farm_id"] = base.get("farm_id").fillna(base["farm_id_pm"])
        base.drop(columns=["farm_id_pm"], inplace=True)
    if "site_id_pm" in base.columns:
        base["site_id"] = base.get("site_id").fillna(base["site_id_pm"])
        base.drop(columns=["site_id_pm"], inplace=True)

    out = (
        base.groupby(["tenant_id", "farm_id", "site_id", "pen_id", "date"], dropna=False)[
            ["cull_events_n", "revenue_cull_rub", "cost_cull_rub"]
        ]
        .sum()
        .reset_index()
    )
    return out

def _build_prices_farm_day_rub(
    *,
    tenant_id: str,
    farms: pd.DataFrame,
    econ_daily: pd.DataFrame,
    prices: pd.DataFrame,
    cfg: Dict[str, Any],
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
    price_overrides: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """Return farm-day table with milk_price_rub_per_kg, feed_cost_rub_per_kg_dm, other_cost_rub_per_farm_day."""

    if farms.empty:
        base = pd.DataFrame({"tenant_id": [tenant_id], "farm_id": ["FARM_001"]})
    else:
        cols = [c for c in ["tenant_id", "farm_id"] if c in farms.columns]
        base = farms[cols].drop_duplicates().copy()
        if "tenant_id" not in base.columns:
            base["tenant_id"] = tenant_id

    days = pd.date_range(date_from, date_to, freq="D")
    base = base.assign(key=1).merge(pd.DataFrame({"date": days, "key": 1}), on="key").drop(columns=["key"])

    # defaults
    defs = (cfg or {}).get("defaults", {}) or {}
    milk_def = defs.get("milk_price", {}) or {}
    feed_def = defs.get("feed_cost", {}) or {}
    other_def = defs.get("other_cost", {}) or {}

    milk_def_val = float(milk_def.get("value_per_kg", 50.0))
    milk_def_ccy = str(milk_def.get("currency", "RUB"))
    feed_def_val = float(feed_def.get("value_per_kg_dm", 30.0))
    feed_def_ccy = str(feed_def.get("currency", "RUB"))
    other_def_val = float(other_def.get("value_per_farm_day", 0.0))
    other_def_ccy = str(other_def.get("currency", "RUB"))

    base["milk_price_rub_per_kg"] = _to_rub(cfg, milk_def_val, milk_def_ccy)
    base["feed_cost_rub_per_kg_dm"] = _to_rub(cfg, feed_def_val, feed_def_ccy)
    base["other_cost_rub_per_farm_day"] = _to_rub(cfg, other_def_val, other_def_ccy)
    base["sources_json"] = json.dumps({"milk_price": "defaults", "feed_cost": "defaults", "other_cost": "defaults"}, ensure_ascii=False)

    # econ_daily overrides
    ed = econ_daily.copy()
    if not ed.empty:
        if "tenant_id" not in ed.columns:
            ed["tenant_id"] = tenant_id
        ed["date"] = pd.to_datetime(ed["date"], errors="coerce").dt.normalize()
        ed = ed.dropna(subset=["tenant_id", "farm_id", "date"])

        # normalize possible columns
        if "other_cost" not in ed.columns:
            if "other_cost_eur" in ed.columns:
                ed["other_cost"] = ed["other_cost_eur"]
                ed["other_cost_ccy"] = "EUR"
            elif "other_cost_rub" in ed.columns:
                ed["other_cost"] = ed["other_cost_rub"]
                ed["other_cost_ccy"] = "RUB"

        # currencies for price/cost from cfg if not given
        in_ccy = str(((cfg or {}).get("inputs", {}) or {}).get("dm_economics_daily_currency", "EUR"))
        if "milk_price_ccy" not in ed.columns:
            ed["milk_price_ccy"] = in_ccy
        if "feed_cost_ccy" not in ed.columns:
            ed["feed_cost_ccy"] = in_ccy
        if "other_cost_ccy" not in ed.columns:
            ed["other_cost_ccy"] = in_ccy

        ov = ed[["tenant_id", "farm_id", "date"]].copy()
        if "milk_price_per_kg" in ed.columns:
            ov["milk_price_rub_per_kg"] = pd.to_numeric(ed["milk_price_per_kg"], errors="coerce") * ed["milk_price_ccy"].map(lambda c: _fx(cfg, str(c)))
        if "feed_cost_per_kg_dm" in ed.columns:
            ov["feed_cost_rub_per_kg_dm"] = pd.to_numeric(ed["feed_cost_per_kg_dm"], errors="coerce") * ed["feed_cost_ccy"].map(lambda c: _fx(cfg, str(c)))
        if "other_cost" in ed.columns:
            ov["other_cost_rub_per_farm_day"] = pd.to_numeric(ed["other_cost"], errors="coerce") * ed["other_cost_ccy"].map(lambda c: _fx(cfg, str(c)))

        ov["sources_json"] = json.dumps({"milk_price": "dm_economics_daily", "feed_cost": "dm_economics_daily", "other_cost": "dm_economics_daily"}, ensure_ascii=False)
        base = base.merge(ov, on=["tenant_id", "farm_id", "date"], how="left", suffixes=("", "_ov"))
        for c in ["milk_price_rub_per_kg", "feed_cost_rub_per_kg_dm", "other_cost_rub_per_farm_day"]:
            if f"{c}_ov" in base.columns:
                base[c] = base[f"{c}_ov"].combine_first(base[c])
                base.drop(columns=[f"{c}_ov"], inplace=True)
        if "sources_json_ov" in base.columns:
            base["sources_json"] = base["sources_json_ov"].combine_first(base["sources_json"])
            base.drop(columns=["sources_json_ov"], inplace=True)

    # dm_prices milk fallback per day if econ_daily missing
    if not prices.empty and {"item_type", "value", "currency"}.issubset(set(prices.columns)):
        pr = prices.copy()
        if "tenant_id" not in pr.columns:
            pr["tenant_id"] = tenant_id
        pr = pr[pr["item_type"].astype(str).str.lower() == "milk"].copy()
        if not pr.empty:
            pr["valid_from"] = pd.to_datetime(pr.get("valid_from"), errors="coerce")
            pr["valid_to"] = pd.to_datetime(pr.get("valid_to"), errors="coerce") if "valid_to" in pr.columns else pd.NaT
            pr = pr.sort_values(["tenant_id", "valid_from"]).dropna(subset=["tenant_id", "valid_from"])
            # create daily mapping per tenant (no farm-specific prices in fixtures)
            # merge_asof on date
            tmp = base[["tenant_id", "farm_id", "date", "milk_price_rub_per_kg", "sources_json"]].copy()
            tmp = tmp.sort_values(["tenant_id", "date"]).reset_index(drop=True)
            pr2 = pr.rename(columns={"value": "milk_price_val"})
            pr2 = pr2[["tenant_id", "valid_from", "milk_price_val", "currency"]]
            pr2 = pr2.sort_values(["tenant_id", "valid_from"])

            merged = pd.merge_asof(
                tmp,
                pr2,
                left_on="date",
                right_on="valid_from",
                by="tenant_id",
                direction="backward",
                allow_exact_matches=True,
            )
            # fill only if still defaults (heuristic: if sources_json says defaults)
            def _is_defaults(s: Any) -> bool:
                try:
                    o = json.loads(str(s))
                    return (o.get("milk_price") == "defaults")
                except Exception:
                    return True

            mask = merged["milk_price_val"].notna() & merged["sources_json"].map(_is_defaults)
            override_price = _float_series(
                pd.to_numeric(merged["milk_price_val"], errors="coerce") * merged["currency"].map(lambda c: _fx(cfg, str(c))),
                index=merged.index,
            )
            _assign_float_where(df=merged, column="milk_price_rub_per_kg", mask=mask, values=override_price)
            merged.loc[mask, "sources_json"] = json.dumps({"milk_price": "dm_prices", "feed_cost": "defaults", "other_cost": "defaults"}, ensure_ascii=False)
            base = base.drop(columns=["milk_price_rub_per_kg", "sources_json"]).merge(
                merged[["tenant_id", "farm_id", "date", "milk_price_rub_per_kg", "sources_json"]],
                on=["tenant_id", "farm_id", "date"],
                how="left",
            )

    # Price book overrides (highest priority): apply to all farm-days.
    if price_overrides:
        try:
            # expected keys: milk.price_per_kg, feed.cost_per_kg_dm, other.cost_per_farm_day
            def _ov(key: str) -> dict | None:
                v = price_overrides.get(key)
                return v if isinstance(v, dict) else None

            milk = _ov("milk.price_per_kg")
            feed = _ov("feed.cost_per_kg_dm")
            other = _ov("other.cost_per_farm_day")

            if milk and milk.get("value") is not None:
                base["milk_price_rub_per_kg"] = _to_rub(cfg, float(milk.get("value")), str(milk.get("currency") or "RUB"))
            if feed and feed.get("value") is not None:
                base["feed_cost_rub_per_kg_dm"] = _to_rub(cfg, float(feed.get("value")), str(feed.get("currency") or "RUB"))
            if other and other.get("value") is not None:
                base["other_cost_rub_per_farm_day"] = _to_rub(cfg, float(other.get("value")), str(other.get("currency") or "RUB"))

            base["sources_json"] = json.dumps(
                {"milk_price": "price_book", "feed_cost": "price_book", "other_cost": "price_book"},
                ensure_ascii=False,
            )
        except Exception:
            # silent fallback: keep computed prices
            pass

    return base[["tenant_id", "farm_id", "date", "milk_price_rub_per_kg", "feed_cost_rub_per_kg_dm", "other_cost_rub_per_farm_day", "sources_json"]].copy()


def _deep_set(cfg: Dict[str, Any], dotted_key: str, value: Any) -> None:
    """Set cfg['a']['b']['c']=value for dotted_key='a.b.c'."""
    if not dotted_key:
        return
    cur: Any = cfg
    parts = [p for p in str(dotted_key).split(".") if p]
    for p in parts[:-1]:
        if not isinstance(cur, dict):
            return
        if p not in cur or not isinstance(cur.get(p), dict):
            cur[p] = {}
        cur = cur[p]
    if isinstance(cur, dict):
        cur[parts[-1]] = value


def _load_refdata(
    *,
    refdata_db_path: Path,
    tenant_id: str,
    price_version: str | None,
    assumptions_version: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None, str | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """Load price/assumptions overrides from sqlite.

    Returns:
      (prices_dict, assumptions_dict, used_price_version, used_assumptions_version, price_items, assumptions_items)
    """
    conn = connect_sqlite(refdata_db_path)
    try:
        store = RefdataStore(conn)
        store.ensure()

        pv = (price_version or store.get_active_version(tenant_id=tenant_id, kind="price_book"))
        av = (assumptions_version or store.get_active_version(tenant_id=tenant_id, kind="assumptions"))

        p_dict: dict[str, Any] | None = None
        a_dict: dict[str, Any] | None = None
        p_items: list[dict[str, Any]] = []
        a_items: list[dict[str, Any]] = []

        if pv:
            if not store.get_price_version(tenant_id=tenant_id, version_id=pv):
                raise ValueError(f"price_version не найден: {pv}")
            p_dict = store.load_prices_as_dict(tenant_id=tenant_id, version_id=pv)
            p_items = store.get_price_items(tenant_id=tenant_id, version_id=pv)

        if av:
            if not store.get_assumptions_version(tenant_id=tenant_id, version_id=av):
                raise ValueError(f"assumptions_version не найден: {av}")
            a_dict = store.load_assumptions_as_dict(tenant_id=tenant_id, version_id=av)
            a_items = store.get_assumptions_items(tenant_id=tenant_id, version_id=av)

        return p_dict, a_dict, pv, av, p_items, a_items
    finally:
        conn.close()


def _allocate_other_cost(
    *,
    pen_day: pd.DataFrame,
    farm_prices: pd.DataFrame,
    method: str,
) -> pd.DataFrame:
    out = pen_day.copy()
    if out.empty:
        out["cost_other_rub"] = 0.0
        return out

    base = out[["tenant_id", "farm_id", "date", "pen_id", "revenue_milk_rub", "milk_kg"]].copy()
    m = (method or "revenue_share").strip().lower()
    if m == "milk_share":
        base["w"] = pd.to_numeric(base["milk_kg"], errors="coerce").fillna(0.0)
    else:
        base["w"] = pd.to_numeric(base["revenue_milk_rub"], errors="coerce").fillna(0.0)

    tot = base.groupby(["tenant_id", "farm_id", "date"], dropna=False)["w"].sum().reset_index().rename(columns={"w": "w_total"})
    base = base.merge(tot, on=["tenant_id", "farm_id", "date"], how="left")

    base["share"] = 0.0
    mask = base["w_total"] > 0
    base.loc[mask, "share"] = base.loc[mask, "w"] / base.loc[mask, "w_total"]

    # if w_total=0 -> equal share
    counts = base.groupby(["tenant_id", "farm_id", "date"], dropna=False)["pen_id"].nunique().reset_index().rename(columns={"pen_id": "n_pens"})
    base = base.merge(counts, on=["tenant_id", "farm_id", "date"], how="left")
    base.loc[~mask, "share"] = 1.0 / base.loc[~mask, "n_pens"].clip(lower=1)

    f = farm_prices[["tenant_id", "farm_id", "date", "other_cost_rub_per_farm_day"]].copy()
    base = base.merge(f, on=["tenant_id", "farm_id", "date"], how="left")
    base["cost_other_rub"] = pd.to_numeric(base["other_cost_rub_per_farm_day"], errors="coerce").fillna(0.0) * base["share"]

    out = out.merge(base[["tenant_id", "farm_id", "date", "pen_id", "cost_other_rub"]], on=["tenant_id", "farm_id", "date", "pen_id"], how="left")
    out["cost_other_rub"] = pd.to_numeric(out.get("cost_other_rub"), errors="coerce").fillna(0.0)
    return out


def _mk_formula_json_pen(row: pd.Series, params: Dict[str, Any]) -> str:
    obj = {
        "currency": "RUB",
        "formulas": {
            "revenue_milk_rub": "milk_kg * milk_price_rub_per_kg",
            "cost_feed_rub": "feed_dm_kg * feed_cost_rub_per_kg_dm",
            "revenue_cull_rub": "revenue_cull_rub (from dm_cull_events or defaults)",
            "cost_cull_rub": "cost_cull_rub (from dm_cull_events or defaults)",
            "cost_vet_rub": "treatments_n * vet_cost_per_treatment_event_rub",
            "cost_repro_rub": "inseminations_n * insemination_cost_rub",
            "cost_other_rub": "allocated_other_cost_rub",
            "total_cost_rub": "cost_feed_rub + cost_vet_rub + cost_repro_rub + cost_cull_rub + cost_other_rub",
            "margin_rub": "revenue_total_rub - total_cost_rub",
            "cost_per_liter_rub": "total_cost_rub / milk_liters",
        },
        "vars": {
            "milk_kg": float(row.get("milk_kg") or 0.0),
            "milk_liters": float(row.get("milk_liters") or 0.0),
            "feed_dm_kg": float(row.get("feed_dm_kg") or 0.0),
            "milk_price_rub_per_kg": float(row.get("milk_price_rub_per_kg") or 0.0),
            "feed_cost_rub_per_kg_dm": float(row.get("feed_cost_rub_per_kg_dm") or 0.0),
            "treatments_n": float(row.get("treatments_n") or 0.0),
            "inseminations_n": float(row.get("inseminations_n") or 0.0),
            "cull_events_n": float(row.get("cull_events_n") or 0.0),
            "revenue_cull_rub": float(row.get("revenue_cull_rub") or 0.0),
            "cost_cull_rub": float(row.get("cost_cull_rub") or 0.0),
            "vet_cost_per_treatment_event_rub": float(params.get("vet_cost_per_treatment_event_rub", 0.0)),
            "insemination_cost_rub": float(params.get("insemination_cost_rub", 0.0)),
            "cull_revenue_per_head_rub": float(params.get("cull_revenue_per_head_rub", 0.0)),
            "cull_cost_per_head_rub": float(params.get("cull_cost_per_head_rub", 0.0)),
            "allocated_other_cost_rub": float(row.get("cost_other_rub") or 0.0),
        },
    }
    return json.dumps(obj, ensure_ascii=False)


def _mk_formula_json_agg(level: str) -> str:
    return json.dumps(
        {
            "currency": "RUB",
            "aggregation": f"level={level}; all numeric fields are SUM over child rows",
            "note": "Производные метрики (cost_per_liter, margin_pct) пересчитываются на агрегатах.",
        },
        ensure_ascii=False,
    )


def run_economics_v2(
    *,
    artifacts_root: Path,
    data_version: str,
    date_from: str,
    date_to: str,
    cfg_path: Path = DEFAULT_CFG_PATH,
    economics_run: Optional[str] = None,
    input_dir: Optional[Path] = None,
    tenant_id: str = "default",
    refdata_db_path: Optional[Path] = None,
    price_version: Optional[str] = None,
    assumptions_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Build economics_daily/economics_monthly (RUB) for a date range."""

    artifacts_root = Path(artifacts_root)
    cfg = _load_cfg(Path(cfg_path))

    # T11-02: optional overrides from refdata (price book + assumptions)
    price_overrides: Dict[str, Any] | None = None
    assumptions_overrides: Dict[str, Any] | None = None
    used_price_version: str | None = None
    used_assumptions_version: str | None = None
    price_snapshot: Dict[str, Any] | None = None
    assumptions_snapshot: Dict[str, Any] | None = None

    if refdata_db_path or price_version or assumptions_version:
        db_path = Path(refdata_db_path) if refdata_db_path else Path(os.environ.get("GENOMEAI_REFDATA_DB", "web_cabinet/storage/web.db"))
        if not db_path.exists():
            raise ValueError(f"Refdata DB не найден: {db_path}. Укажите --refdata-db или GENOMEAI_REFDATA_DB")
        conn = connect_sqlite(db_path)
        try:
            store = RefdataStore(conn)
            store.ensure()

            # resolve versions: explicit arg > active pointer
            if price_version:
                used_price_version = str(price_version)
            else:
                used_price_version = store.get_active_version(tenant_id=tenant_id, kind="price_book")
            if assumptions_version:
                used_assumptions_version = str(assumptions_version)
            else:
                used_assumptions_version = store.get_active_version(tenant_id=tenant_id, kind="assumptions")

            if used_price_version:
                if not store.get_price_version(tenant_id=tenant_id, version_id=used_price_version):
                    raise ValueError(f"Price book version_id не найден: {used_price_version}")
                price_overrides = store.load_prices_as_dict(tenant_id=tenant_id, version_id=used_price_version)
                price_snapshot = {
                    "version": store.get_price_version(tenant_id=tenant_id, version_id=used_price_version),
                    "items": store.get_price_items(tenant_id=tenant_id, version_id=used_price_version),
                }

            if used_assumptions_version:
                if not store.get_assumptions_version(tenant_id=tenant_id, version_id=used_assumptions_version):
                    raise ValueError(f"Assumptions version_id не найден: {used_assumptions_version}")
                assumptions_overrides = store.load_assumptions_as_dict(tenant_id=tenant_id, version_id=used_assumptions_version)
                assumptions_snapshot = {
                    "version": store.get_assumptions_version(tenant_id=tenant_id, version_id=used_assumptions_version),
                    "items": store.get_assumptions_items(tenant_id=tenant_id, version_id=used_assumptions_version),
                }

        finally:
            conn.close()

    # apply assumptions overrides into cfg (dotted keys)
    if assumptions_overrides:
        for k, v in assumptions_overrides.items():
            if v is None:
                continue
            _deep_set(cfg, str(k), v)

    try:
        d1 = pd.to_datetime(date_from)
        d2 = pd.to_datetime(date_to)
        if pd.isna(d1) or pd.isna(d2):
            raise ValueError("bad dates")
        d1 = d1.normalize()
        d2 = d2.normalize()
    except Exception:
        raise ValueError(f"Неверные даты date_from/date_to: '{date_from}'..'{date_to}'")

    if d2 < d1:
        raise ValueError("date_to < date_from")

    canonical = _resolve_canonical_dir(artifacts_root, data_version, input_dir=input_dir)

    farms = _read_table(canonical, "dm_farms")
    milkings = _read_table(canonical, "dm_milkings_daily")
    animals = _read_table(canonical, "dm_animals")
    pen_moves = _read_table(canonical, "dm_pen_moves")
    pens = _read_table(canonical, "dm_pens")
    sites = _read_table(canonical, "dm_sites")
    deliveries = _read_table(canonical, "dm_feed_deliveries")
    rations = _read_table(canonical, "dm_feed_rations")
    econ_daily = _read_table(canonical, "dm_economics_daily")
    prices = _read_table(canonical, "dm_prices")
    treatments = _read_table(canonical, "dm_treatments")
    repro = _read_table(canonical, "dm_repro_events")
    cull_events = _read_table(canonical, "dm_cull_events")

    # sanity: some fixtures may have dm_testday instead of dm_milkings_daily
    if milkings.empty:
        td = _read_table(canonical, "dm_testday")
        if not td.empty and {"animal_id", "date", "milk_kg"}.issubset(set(td.columns)):
            base = td[["animal_id", "date", "milk_kg"]].copy()
            base["tenant_id"] = tenant_id
            milkings = base

    # parse dates in inputs
    for df, col in [
        (milkings, "date"),
        (deliveries, "delivery_date"),
        (pen_moves, "move_date"),
        (econ_daily, "date"),
        (prices, "valid_from"),
        (treatments, "start_date"),
        (repro, "event_date"),
        (cull_events, "event_date"),
    ]:
        if not df.empty and col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    pen_map = _build_pen_map(pens, sites)

    farm_prices = _build_prices_farm_day_rub(
        tenant_id=tenant_id,
        farms=farms,
        econ_daily=econ_daily,
        prices=prices,
        cfg=cfg,
        date_from=d1,
        date_to=d2,
        price_overrides=price_overrides,
    )

    milk_pen = _build_milk_pen_day(
        milkings=milkings,
        animals=animals,
        pen_moves=pen_moves,
        pen_map=pen_map,
        date_from=d1,
        date_to=d2,
    )
    feed_pen = _build_feed_pen_day(
        deliveries=deliveries,
        rations=rations,
        pen_map=pen_map,
        date_from=d1,
        date_to=d2,
    )
    vet_pen = _build_treatments_pen_day(
        treatments=treatments,
        animals=animals,
        pen_moves=pen_moves,
        pen_map=pen_map,
        date_from=d1,
        date_to=d2,
    )
    repro_pen = _build_repro_pen_day(
        repro_events=repro,
        animals=animals,
        pen_moves=pen_moves,
        pen_map=pen_map,
        date_from=d1,
        date_to=d2,
    )

    cull_pen = _build_cull_pen_day(
        cull_events=cull_events,
        animals=animals,
        pen_moves=pen_moves,
        pen_map=pen_map,
        cfg=cfg,
        date_from=d1,
        date_to=d2,
    )

    # join pen-level
    pen_day = milk_pen.merge(feed_pen, on=["tenant_id", "farm_id", "site_id", "pen_id", "pen_name", "pen_type", "date"], how="outer")
    pen_day = pen_day.merge(vet_pen, on=["tenant_id", "farm_id", "site_id", "pen_id", "date"], how="outer")
    pen_day = pen_day.merge(repro_pen, on=["tenant_id", "farm_id", "site_id", "pen_id", "date"], how="outer")
    pen_day = pen_day.merge(cull_pen, on=["tenant_id", "farm_id", "site_id", "pen_id", "date"], how="outer")

    # fill pen_name/pen_type for rows that come only from events
    pen_day = pen_day.merge(pen_map[["tenant_id", "pen_id", "pen_name", "pen_type"]], on=["tenant_id", "pen_id"], how="left", suffixes=("", "_pm"))
    if "pen_name_pm" in pen_day.columns:
        pen_day["pen_name"] = pen_day.get("pen_name").combine_first(pen_day["pen_name_pm"])
        pen_day.drop(columns=["pen_name_pm"], inplace=True)
    if "pen_type_pm" in pen_day.columns:
        pen_day["pen_type"] = pen_day.get("pen_type").combine_first(pen_day["pen_type_pm"])
        pen_day.drop(columns=["pen_type_pm"], inplace=True)

    for c in ["milk_kg", "feed_dm_kg", "treatments_n", "inseminations_n", "cull_events_n", "revenue_cull_rub", "cost_cull_rub"]:
        pen_day[c] = pd.to_numeric(pen_day.get(c), errors="coerce").fillna(0.0)

    pen_day["milk_liters"] = pen_day["milk_kg"]

    # prices
    pen_day = pen_day.merge(farm_prices, on=["tenant_id", "farm_id", "date"], how="left")
    for c in ["milk_price_rub_per_kg", "feed_cost_rub_per_kg_dm", "other_cost_rub_per_farm_day"]:
        pen_day[c] = pd.to_numeric(pen_day.get(c), errors="coerce").fillna(0.0)

    pen_day["revenue_milk_rub"] = pen_day["milk_kg"] * pen_day["milk_price_rub_per_kg"]
    pen_day["cost_feed_rub"] = pen_day["feed_dm_kg"] * pen_day["feed_cost_rub_per_kg_dm"]

    cm = (cfg or {}).get("cost_models", {}) or {}
    vet_cfg = cm.get("vet", {}) or {}
    repro_cfg = cm.get("repro", {}) or {}
    vet_cost = float(vet_cfg.get("cost_per_treatment_event_rub", 0.0))
    insemin_cost = float(repro_cfg.get("insemination_cost_rub", 0.0))

    pen_day["cost_vet_rub"] = pen_day["treatments_n"] * vet_cost
    pen_day["cost_repro_rub"] = pen_day["inseminations_n"] * insemin_cost

    # allocate other cost
    alloc = (cfg or {}).get("allocation", {}) or {}
    pen_day = _allocate_other_cost(pen_day=pen_day, farm_prices=farm_prices, method=str(alloc.get("other_cost_allocation", "revenue_share")))

    pen_day["revenue_total_rub"] = pen_day["revenue_milk_rub"] + pen_day["revenue_cull_rub"]
    pen_day["total_cost_rub"] = pen_day["cost_feed_rub"] + pen_day["cost_vet_rub"] + pen_day["cost_repro_rub"] + pen_day["cost_cull_rub"] + pen_day["cost_other_rub"]
    pen_day["margin_rub"] = pen_day["revenue_total_rub"] - pen_day["total_cost_rub"]

    pen_day["margin_pct"] = 0.0
    mask = pen_day["revenue_total_rub"] > 0
    pen_day.loc[mask, "margin_pct"] = pen_day.loc[mask, "margin_rub"] / pen_day.loc[mask, "revenue_total_rub"]

    pen_day["cost_per_liter_rub"] = float("nan")
    mask2 = pen_day["milk_liters"] > 0
    pen_day.loc[mask2, "cost_per_liter_rub"] = pen_day.loc[mask2, "total_cost_rub"] / pen_day.loc[mask2, "milk_liters"]

    cm = (cfg or {}).get("cost_models", {}) or {}
    cull_cfg = cm.get("cull", {}) or {}
    cull_rev_def = float(cull_cfg.get("revenue_per_head_rub", 0.0))
    cull_cost_def = float(cull_cfg.get("cost_per_head_rub", 0.0))

    params = {
        "vet_cost_per_treatment_event_rub": vet_cost,
        "insemination_cost_rub": insemin_cost,
        "cull_revenue_per_head_rub": cull_rev_def,
        "cull_cost_per_head_rub": cull_cost_def,
    }
    pen_day["formula_json"] = pen_day.apply(lambda r: _mk_formula_json_pen(r, params), axis=1)

    # derive site-day and farm-day
    num_cols = [
        "milk_kg",
        "milk_liters",
        "feed_dm_kg",
        "treatments_n",
        "inseminations_n",
        "cull_events_n",
        "revenue_milk_rub",
        "revenue_cull_rub",
        "revenue_total_rub",
        "cost_feed_rub",
        "cost_vet_rub",
        "cost_repro_rub",
        "cost_cull_rub",
        "cost_other_rub",
        "total_cost_rub",
        "margin_rub",
    ]

    site_day = pen_day.groupby(["tenant_id", "farm_id", "site_id", "date"], dropna=False)[num_cols].sum().reset_index()
    site_day["margin_pct"] = 0.0
    m3 = site_day["revenue_total_rub"] > 0
    site_day.loc[m3, "margin_pct"] = site_day.loc[m3, "margin_rub"] / site_day.loc[m3, "revenue_total_rub"]
    site_day["cost_per_liter_rub"] = float("nan")
    m4 = site_day["milk_liters"] > 0
    site_day.loc[m4, "cost_per_liter_rub"] = site_day.loc[m4, "total_cost_rub"] / site_day.loc[m4, "milk_liters"]
    site_day["pen_id"] = pd.NA
    site_day["pen_name"] = pd.NA
    site_day["pen_type"] = pd.NA
    site_day["milk_price_rub_per_kg"] = pd.NA
    site_day["feed_cost_rub_per_kg_dm"] = pd.NA
    site_day["other_cost_rub_per_farm_day"] = pd.NA
    site_day["sources_json"] = pd.NA
    site_day["formula_json"] = _mk_formula_json_agg("site")

    farm_day = site_day.groupby(["tenant_id", "farm_id", "date"], dropna=False)[num_cols].sum().reset_index()
    farm_day["margin_pct"] = 0.0
    m5 = farm_day["revenue_total_rub"] > 0
    farm_day.loc[m5, "margin_pct"] = farm_day.loc[m5, "margin_rub"] / farm_day.loc[m5, "revenue_total_rub"]
    farm_day["cost_per_liter_rub"] = float("nan")
    m6 = farm_day["milk_liters"] > 0
    farm_day.loc[m6, "cost_per_liter_rub"] = farm_day.loc[m6, "total_cost_rub"] / farm_day.loc[m6, "milk_liters"]

    farm_day["site_id"] = pd.NA
    farm_day["pen_id"] = pd.NA
    farm_day["pen_name"] = pd.NA
    farm_day["pen_type"] = pd.NA
    farm_day["milk_price_rub_per_kg"] = pd.NA
    farm_day["feed_cost_rub_per_kg_dm"] = pd.NA
    farm_day["other_cost_rub_per_farm_day"] = pd.NA
    farm_day["sources_json"] = pd.NA
    farm_day["formula_json"] = _mk_formula_json_agg("farm")

    pen_out = pen_day.copy()
    pen_out["level"] = "pen"
    site_day["level"] = "site"
    farm_day["level"] = "farm"

    cols_order = [
        "level",
        "tenant_id",
        "farm_id",
        "site_id",
        "pen_id",
        "pen_name",
        "pen_type",
        "date",
        "milk_kg",
        "milk_liters",
        "feed_dm_kg",
        "treatments_n",
        "inseminations_n",
        "cull_events_n",
        "milk_price_rub_per_kg",
        "feed_cost_rub_per_kg_dm",
        "other_cost_rub_per_farm_day",
        "revenue_milk_rub",
        "revenue_cull_rub",
        "revenue_total_rub",
        "cost_feed_rub",
        "cost_vet_rub",
        "cost_repro_rub",
        "cost_cull_rub",
        "cost_other_rub",
        "total_cost_rub",
        "margin_rub",
        "margin_pct",
        "cost_per_liter_rub",
        "sources_json",
        "formula_json",
    ]

    econ_daily_out = _concat_legacy_compatible([pen_out, site_day, farm_day])
    # ensure cols
    for c in cols_order:
        if c not in econ_daily_out.columns:
            econ_daily_out[c] = pd.NA
    econ_daily_out = econ_daily_out[cols_order].copy()

    # monthly
    econ_daily_out["month"] = pd.to_datetime(econ_daily_out["date"], errors="coerce").dt.to_period("M").astype(str)
    gcols = ["level", "tenant_id", "farm_id", "site_id", "pen_id", "pen_name", "pen_type", "month"]
    econ_month = econ_daily_out.groupby(gcols, dropna=False)[num_cols].sum().reset_index()
    econ_month["margin_pct"] = 0.0
    mm = econ_month["revenue_total_rub"] > 0
    econ_month.loc[mm, "margin_pct"] = econ_month.loc[mm, "margin_rub"] / econ_month.loc[mm, "revenue_total_rub"]
    econ_month["cost_per_liter_rub"] = pd.NA
    mm2 = econ_month["milk_liters"] > 0
    econ_month.loc[mm2, "cost_per_liter_rub"] = econ_month.loc[mm2, "total_cost_rub"] / econ_month.loc[mm2, "milk_liters"]
    econ_month["currency"] = "RUB"
    econ_month["formula_json"] = econ_month["level"].map(lambda lv: _mk_formula_json_agg(str(lv)))

    econ_daily_out["currency"] = "RUB"

    rid = economics_run or generate_run_id(prefix="econ2")
    run_dir = Path(artifacts_root) / data_version / "economics_v2" / rid
    run_dir.mkdir(parents=True, exist_ok=True)

    # write outputs
    econ_daily_out.to_csv(run_dir / "economics_daily.csv", index=False)
    econ_month.to_csv(run_dir / "economics_monthly.csv", index=False)

    # T11-02: snapshot refdata used in this run (to guarantee reproducibility)
    refdata_manifest: Dict[str, Any] = {
        "price_book_version": used_price_version,
        "assumptions_version": used_assumptions_version,
    }
    if used_price_version and price_snapshot:
        write_json(run_dir / "refdata_price_book.json", price_snapshot)
        refdata_manifest["price_book_file"] = "refdata_price_book.json"
    if used_assumptions_version and assumptions_snapshot:
        write_json(run_dir / "refdata_assumptions.json", assumptions_snapshot)
        refdata_manifest["assumptions_file"] = "refdata_assumptions.json"
    if used_price_version or used_assumptions_version:
        write_json(run_dir / "refdata_used.json", refdata_manifest)

    formulas_catalog = {
        "schema": "genomeai.economics.formulas_catalog.v1",
        "currency": "RUB",
        "pen_level": {
            "revenue_milk_rub": "milk_kg * milk_price_rub_per_kg",
            "cost_feed_rub": "feed_dm_kg * feed_cost_rub_per_kg_dm",
            "cost_vet_rub": "treatments_n * vet_cost_per_treatment_event_rub",
            "revenue_cull_rub": "SUM(cull events revenue) or cull_events_n * cull_revenue_per_head_rub",
            "cost_cull_rub": "SUM(cull events cost) or cull_events_n * cull_cost_per_head_rub",
            "cost_repro_rub": "inseminations_n * insemination_cost_rub",
            "cost_other_rub": "allocated other_cost_rub_per_farm_day",
            "total_cost_rub": "cost_feed_rub + cost_vet_rub + cost_repro_rub + cost_cull_rub + cost_other_rub",
            "margin_rub": "revenue_total_rub - total_cost_rub",
            "cost_per_liter_rub": "total_cost_rub / milk_liters",
        },
        "aggregation_levels": {
            "site": "SUM over child pen rows",
            "farm": "SUM over child site/pen rows",
        },
        "cost_models": params,
    }
    write_json(run_dir / "formulas_catalog.json", formulas_catalog)

    manifest = {
        "schema": "genomeai.economics_v2.manifest.v1",
        "created_at": _utc_ts(),
        "tenant_id": tenant_id,
        "data_version": data_version,
        "economics_run": rid,
        "date_from": str(d1.date()),
        "date_to": str(d2.date()),
        "currency": "RUB",
        "cfg_path": str(Path(cfg_path)),
        "inputs": {
            "canonical_dir": str(canonical),
            "datasets": {
                "dm_milkings_daily": "dm_milkings_daily",
                "dm_feed_deliveries": "dm_feed_deliveries",
                "dm_feed_rations": "dm_feed_rations",
                "dm_economics_daily": "dm_economics_daily",
                "dm_prices": "dm_prices",
                "dm_treatments": "dm_treatments",
                "dm_repro_events": "dm_repro_events",
                "dm_cull_events": "dm_cull_events",
            },
        },
        "versions": {
            "data_version": data_version,
            "economics_run": rid,
            "price_book_version": used_price_version,
            "assumptions_version": used_assumptions_version,
        },
        "refdata": refdata_manifest,
        "limitations": [
            "Vet/Repro cost models: упрощённые (стоимость на событие начала лечения/осеменения); величины задаются в configs/economics/economics_v2.yaml.",
            "Cull model: выручка/затраты берутся из dm_cull_events (revenue_rub/cost_rub) или из defaults (revenue_per_head_rub/cost_per_head_rub).",
        ],
    }
    write_json(run_dir / "manifest.json", manifest)

    # also write Target run layout
    run_root = ensure_run_dir(artifacts_root, data_version, rid)
    out_sub = run_root / "economics_v2"
    out_sub.mkdir(parents=True, exist_ok=True)
    for name in ["economics_daily.csv", "economics_monthly.csv", "formulas_catalog.json", "manifest.json"]:
        p = run_dir / name
        if p.exists():
            (out_sub / name).write_bytes(p.read_bytes())

    run_manifest = {
        "schema": "genomeai.run_manifest.v1",
        "step": "economics_v2",
        "data_version": data_version,
        "run_id": rid,
        "created_at": manifest["created_at"],
        "status": "DONE",
        "outputs": {
            "legacy_dir": str(run_dir.resolve()),
            "run_dir": str(out_sub.resolve()),
            "economics_daily": str((out_sub / "economics_daily.csv").resolve()),
            "economics_monthly": str((out_sub / "economics_monthly.csv").resolve()),
        },
        "params": {
            "date_from": str(d1.date()),
            "date_to": str(d2.date()),
            "currency": "RUB",
            "price_book_version": used_price_version,
            "assumptions_version": used_assumptions_version,
        },
    }
    write_run_manifest(run_root=run_root, manifest=run_manifest)
    write_checksums(run_root=run_root, include_subdirs=["economics_v2"])

    # per-data_version metadata manifest
    meta_dir = Path(artifacts_root) / data_version / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta_path = meta_dir / "economics_v2_manifest.json"
    if meta_path.exists():
        try:
            mobj = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            mobj = {}
    else:
        mobj = {"schema": "genomeai.economics_v2_manifest.v1", "data_version": data_version, "runs": {}, "latest": None}

    mobj.setdefault("runs", {})
    mobj["runs"][rid] = {
        "created_at": manifest["created_at"],
        "date_from": str(d1.date()),
        "date_to": str(d2.date()),
        "currency": "RUB",
        "price_book_version": used_price_version,
        "assumptions_version": used_assumptions_version,
        "dir": str(run_dir.resolve()),
        "economics_daily": str((run_dir / "economics_daily.csv").resolve()),
        "economics_monthly": str((run_dir / "economics_monthly.csv").resolve()),
    }
    mobj["latest"] = rid
    write_json(meta_path, mobj)

    return {
        "ok": True,
        "data_version": data_version,
        "economics_run": rid,
        "run_dir": str(run_dir.resolve()),
        "outputs": {
            "economics_daily": str((run_dir / "economics_daily.csv").resolve()),
            "economics_monthly": str((run_dir / "economics_monthly.csv").resolve()),
        },
    }


def list_economics_v2_runs(*, artifacts_root: Path, data_version: str) -> list[str]:
    meta_path = Path(artifacts_root) / data_version / "metadata" / "economics_v2_manifest.json"
    if not meta_path.exists():
        return []
    try:
        obj = json.loads(meta_path.read_text(encoding="utf-8"))
        runs = list((obj or {}).get("runs", {}).keys())
        return sorted(runs)
    except Exception:
        return []


def load_economics_v2(
    *,
    artifacts_root: Path,
    data_version: str,
    economics_run: Optional[str] = None,
) -> Tuple[str, Dict[str, pd.DataFrame], Path]:
    """Load economics v2 run. If economics_run is None, loads latest (by metadata manifest) or last dir."""
    root = Path(artifacts_root) / data_version / "economics_v2"

    rid: Optional[str] = economics_run
    if rid is None:
        meta_path = Path(artifacts_root) / data_version / "metadata" / "economics_v2_manifest.json"
        if meta_path.exists():
            try:
                obj = json.loads(meta_path.read_text(encoding="utf-8"))
                rid = (obj or {}).get("latest")
            except Exception:
                rid = None

    if rid is None:
        # fallback to newest dir by mtime
        if not root.exists():
            raise FileNotFoundError("Нет economics_v2 запусков")
        dirs = [p for p in root.iterdir() if p.is_dir()]
        if not dirs:
            raise FileNotFoundError("Нет economics_v2 запусков")
        dirs = sorted(dirs, key=lambda p: p.stat().st_mtime, reverse=True)
        rid = dirs[0].name

    run_dir = root / str(rid)
    if not run_dir.exists():
        raise FileNotFoundError(f"Нет economics_v2 run: {rid}")

    def _rd_csv(name: str) -> pd.DataFrame:
        p = run_dir / name
        return pd.read_csv(p) if p.exists() else pd.DataFrame()

    dfs = {
        "economics_daily": _rd_csv("economics_daily.csv"),
        "economics_monthly": _rd_csv("economics_monthly.csv"),
    }
    return str(rid), dfs, run_dir

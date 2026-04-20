from __future__ import annotations

"""T7-01: Экономика / what-if (прозрачные формулы).

Назначение:
 - Описать входные цены/затраты и периодичность обновления
 - Рассчитать простую маржу по ферме/группе/периоду
 - Сценарии what-if: изменение цены молока/корма/прочих затрат -> пересчёт маржи

Ключевой принцип:
 - UI (Streamlit) ничего не считает. Он вызывает этот модуль (offline-core) и читает артефакты.

Источники (каноникал):
 - dm_milkings_daily: animal_id, date, milk_kg
 - dm_animals: animal_id, farm_id, current_pen_id
 - dm_pen_moves (опционально): исторические перемещения по pens
 - dm_feed_deliveries + dm_feed_rations: feed_kg_as_fed * dm_pct => kg_dm
 - dm_pens + dm_sites: pen_id -> farm_id
 - dm_economics_daily (опционально): цены и прочие расходы по farm-day
 - dm_prices (опционально): fallback цены (milk)

Артефакты:
  artifacts/<data_version>/economics/<economics_run>/
    - farm_day_baseline.csv
    - pen_day_baseline.csv
    - farm_day_scenario.csv
    - pen_day_scenario.csv
    - summary_farm.csv
    - summary_pen.csv
    - whatif_params.json
    - economics_whatif.xlsx
    - manifest.json
    - checksums.json

Ограничения точности:
 - Если нет dm_economics_daily, применяются fallback значения из configs/economics/economics_v1.yaml.
 - Прочие затраты (other_cost) распределяются по группам по выбранному правилу allocation.
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from .versioning import generate_run_id, write_checksums, write_json


DEFAULT_CFG_PATH = Path("configs/economics/economics_v1.yaml")


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

        obj = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _parse_date(s: Any) -> pd.Timestamp:
    return pd.to_datetime(s, errors="coerce", utc=False)


def _date_range(date_from: str, date_to: str) -> Tuple[pd.Timestamp, pd.Timestamp]:
    d1 = pd.to_datetime(date_from)
    d2 = pd.to_datetime(date_to)
    if pd.isna(d1) or pd.isna(d2):
        raise ValueError("Некорректный диапазон дат")
    if d2 < d1:
        d1, d2 = d2, d1
    return d1.normalize(), d2.normalize()


def _latest_run_dir(root: Path) -> Optional[Path]:
    if not root.exists():
        return None
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if not dirs:
        return None
    return sorted(dirs, key=lambda p: p.name)[-1]


@dataclass(frozen=True)
class EconomicsRunResult:
    ok: bool
    economics_run: str
    data_version: str
    run_dir: str
    reason: Optional[str] = None


def _assign_pen_on_date(
    milk: pd.DataFrame,
    animals: pd.DataFrame,
    pen_moves: pd.DataFrame,
) -> pd.DataFrame:
    """Assign pen_id to each milking record using latest move <= date, fallback to animals.current_pen_id."""
    out = milk.copy()
    if out.empty:
        out["pen_id"] = None
        return out

    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()

    a = animals[["animal_id", "farm_id", "current_pen_id"]].copy() if not animals.empty else pd.DataFrame(
        columns=["animal_id", "farm_id", "current_pen_id"]
    )
    out = out.merge(a, on="animal_id", how="left")
    out.rename(columns={"current_pen_id": "pen_id"}, inplace=True)

    if pen_moves.empty:
        return out

    pm = pen_moves.copy()
    for c in ["move_date"]:
        if c in pm.columns:
            pm[c] = pd.to_datetime(pm[c], errors="coerce").dt.normalize()
    pm = pm.sort_values(["animal_id", "move_date"]).dropna(subset=["animal_id", "move_date"])

    # asof merge per animal: create key, then merge_asof
    # (pandas merge_asof requires sorted by on and by)
    out = out.sort_values(["animal_id", "date"]).reset_index(drop=True)

    pm = pm.rename(columns={"to_pen_id": "pen_id_move"})
    pm = pm[["animal_id", "move_date", "pen_id_move"]]

    merged = pd.merge_asof(
        out,
        pm,
        left_on="date",
        right_on="move_date",
        by="animal_id",
        direction="backward",
        allow_exact_matches=True,
    )
    merged["pen_id"] = merged["pen_id_move"].fillna(merged["pen_id"])
    return merged.drop(columns=[c for c in ["move_date", "pen_id_move"] if c in merged.columns])


def _build_prices_farm_day(
    *,
    econ_daily: pd.DataFrame,
    prices: pd.DataFrame,
    farms: pd.DataFrame,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
    cfg: Dict[str, Any],
) -> pd.DataFrame:
    """Return farm-day table with milk_price_per_kg, feed_cost_per_kg_dm, other_cost."""
    # base farm list
    if farms.empty:
        farm_ids = ["FARM_001"]
        tenant = "default"
        base = pd.DataFrame({"tenant_id": [tenant] * len(farm_ids), "farm_id": farm_ids})
    else:
        base = farms[["tenant_id", "farm_id"]].drop_duplicates().copy()

    days = pd.date_range(date_from, date_to, freq="D")
    base = base.assign(key=1).merge(pd.DataFrame({"date": days, "key": 1}), on="key").drop(columns=["key"])

    defaults = (cfg or {}).get("defaults", {})
    milk_fallback = float(defaults.get("milk_price_per_kg", 0.5))
    feed_fallback = float(defaults.get("feed_cost_per_kg_dm", 0.28))
    other_fallback = float(defaults.get("other_cost_per_farm_day", 120.0))

    # econ_daily override
    ed = econ_daily.copy()
    if not ed.empty:
        ed["date"] = pd.to_datetime(ed["date"], errors="coerce").dt.normalize()
        # normalize column names
        col_map = {
            "milk_price_per_kg": "milk_price_per_kg",
            "milk_price_per_kg_eur": "milk_price_per_kg",
            "milk_price_per_kg": "milk_price_per_kg",
            "feed_cost_per_kg_dm": "feed_cost_per_kg_dm",
            "other_cost_eur": "other_cost",
            "other_cost": "other_cost",
        }
        for k, v in list(col_map.items()):
            if k in ed.columns and v not in ed.columns:
                ed.rename(columns={k: v}, inplace=True)
        keep = [c for c in ["tenant_id", "farm_id", "date", "milk_price_per_kg", "feed_cost_per_kg_dm", "other_cost"] if c in ed.columns]
        ed = ed[keep]

    out = base.merge(ed, on=["tenant_id", "farm_id", "date"], how="left")

    # prices fallback for milk if missing
    mp = out["milk_price_per_kg"] if "milk_price_per_kg" in out.columns else pd.Series([pd.NA] * len(out))
    if prices.empty:
        out["milk_price_per_kg"] = mp.fillna(milk_fallback)
    else:
        pr = prices.copy()
        for c in ["valid_from", "valid_to"]:
            if c in pr.columns:
                pr[c] = pd.to_datetime(pr[c], errors="coerce").dt.normalize()
        pr = pr[pr["item_type"].astype(str).str.lower() == "milk"].copy() if "item_type" in pr.columns else pr
        if "value" in pr.columns:
            pr["value"] = pd.to_numeric(pr["value"], errors="coerce")

        # for each row in out, pick price where valid_from<=date<=valid_to (or valid_to null)
        # use merge_asof on valid_from then filter by valid_to
        pr2 = pr.sort_values(["tenant_id", "valid_from"]).dropna(subset=["tenant_id", "valid_from"])
        tmp = out.sort_values(["tenant_id", "date"]).copy()
        tmp = pd.merge_asof(tmp, pr2, left_on="date", right_on="valid_from", by="tenant_id", direction="backward")
        if "valid_to" in tmp.columns:
            ok = tmp["valid_to"].isna() | (tmp["date"] <= tmp["valid_to"])
            tmp.loc[~ok, "value"] = pd.NA
        price_series = pd.to_numeric(tmp.get("value"), errors="coerce")
        out["milk_price_per_kg"] = mp.fillna(price_series).fillna(milk_fallback)

    out["feed_cost_per_kg_dm"] = pd.to_numeric(out.get("feed_cost_per_kg_dm"), errors="coerce").fillna(feed_fallback)
    out["other_cost"] = pd.to_numeric(out.get("other_cost"), errors="coerce").fillna(other_fallback)
    return out[["tenant_id", "farm_id", "date", "milk_price_per_kg", "feed_cost_per_kg_dm", "other_cost"]]


def _build_feed_pen_day(
    *,
    deliveries: pd.DataFrame,
    rations: pd.DataFrame,
    pens: pd.DataFrame,
    sites: pd.DataFrame,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
) -> pd.DataFrame:
    """Return pen-day feed dm kg delivered."""
    if deliveries.empty:
        return pd.DataFrame(columns=["tenant_id", "farm_id", "pen_id", "date", "feed_dm_kg"])
    d = deliveries.copy()
    d["date"] = pd.to_datetime(d.get("delivery_date", d.get("date")), errors="coerce").dt.normalize()
    d = d[(d["date"] >= date_from) & (d["date"] <= date_to)].copy()
    d["feed_kg_as_fed"] = pd.to_numeric(d.get("feed_kg_as_fed"), errors="coerce")
    d = d.dropna(subset=["tenant_id", "pen_id", "ration_id", "date", "feed_kg_as_fed"])

    r = rations.copy() if not rations.empty else pd.DataFrame(columns=["tenant_id", "ration_id", "dm_pct"])
    r["dm_pct"] = pd.to_numeric(r.get("dm_pct"), errors="coerce")
    d = d.merge(r[["tenant_id", "ration_id", "dm_pct"]], on=["tenant_id", "ration_id"], how="left")
    d["dm_pct"] = d["dm_pct"].fillna(50.0)
    d["feed_dm_kg"] = d["feed_kg_as_fed"] * (d["dm_pct"] / 100.0)

    # pen -> farm mapping
    pen_map = pens[["tenant_id", "pen_id", "site_id", "pen_type"]].copy() if not pens.empty else pd.DataFrame(
        columns=["tenant_id", "pen_id", "site_id", "pen_type"]
    )
    site_map = sites[["tenant_id", "site_id", "farm_id"]].copy() if not sites.empty else pd.DataFrame(
        columns=["tenant_id", "site_id", "farm_id"]
    )
    pen_map = pen_map.merge(site_map, on=["tenant_id", "site_id"], how="left")
    d = d.merge(pen_map[["tenant_id", "pen_id", "farm_id", "pen_type"]], on=["tenant_id", "pen_id"], how="left")

    out = (
        d.groupby(["tenant_id", "farm_id", "pen_id", "pen_type", "date"], dropna=False)["feed_dm_kg"].sum().reset_index()
    )
    return out


def _build_milk_pen_day(
    *,
    milkings: pd.DataFrame,
    animals: pd.DataFrame,
    pen_moves: pd.DataFrame,
    pens: pd.DataFrame,
    sites: pd.DataFrame,
    date_from: pd.Timestamp,
    date_to: pd.Timestamp,
) -> pd.DataFrame:
    if milkings.empty:
        return pd.DataFrame(columns=["tenant_id", "farm_id", "pen_id", "pen_type", "date", "milk_kg"])
    m = milkings[[c for c in ["tenant_id", "animal_id", "date", "milk_kg"] if c in milkings.columns]].copy()
    m["date"] = pd.to_datetime(m["date"], errors="coerce").dt.normalize()
    m = m[(m["date"] >= date_from) & (m["date"] <= date_to)].copy()
    m["milk_kg"] = pd.to_numeric(m.get("milk_kg"), errors="coerce")
    m = m.dropna(subset=["tenant_id", "animal_id", "date", "milk_kg"])

    assigned = _assign_pen_on_date(m, animals, pen_moves)

    # enrich pen_type and farm_id if missing
    if "farm_id" not in assigned.columns:
        assigned["farm_id"] = None
    pen_map = pens[["tenant_id", "pen_id", "site_id", "pen_type"]].copy() if not pens.empty else pd.DataFrame(
        columns=["tenant_id", "pen_id", "site_id", "pen_type"]
    )
    site_map = sites[["tenant_id", "site_id", "farm_id"]].copy() if not sites.empty else pd.DataFrame(
        columns=["tenant_id", "site_id", "farm_id"]
    )
    pen_map = pen_map.merge(site_map, on=["tenant_id", "site_id"], how="left")
    assigned = assigned.merge(
        pen_map[["tenant_id", "pen_id", "farm_id", "pen_type"]],
        on=["tenant_id", "pen_id"],
        how="left",
        suffixes=("", "_pen"),
    )
    if "farm_id_pen" in assigned.columns:
        assigned["farm_id"] = assigned["farm_id"].fillna(assigned["farm_id_pen"])
    if "pen_type" not in assigned.columns:
        assigned["pen_type"] = pd.NA
    if "pen_type_pen" in assigned.columns:
        assigned["pen_type"] = assigned["pen_type"].fillna(assigned["pen_type_pen"])
    for c in ["farm_id_pen", "pen_type_pen"]:
        if c in assigned.columns:
            assigned.drop(columns=[c], inplace=True)

    out = assigned.groupby(["tenant_id", "farm_id", "pen_id", "pen_type", "date"], dropna=False)["milk_kg"].sum().reset_index()
    return out


def _allocate_other_cost_to_pens(
    *,
    pen_day: pd.DataFrame,
    farm_day: pd.DataFrame,
    method: str,
) -> pd.DataFrame:
    out = pen_day.copy()
    if out.empty:
        out["other_cost"] = 0.0
        return out

    method = (method or "revenue_share").strip().lower()
    base = out[["tenant_id", "farm_id", "date", "pen_id", "pen_type", "revenue"]].copy()
    if method == "headcount_share" and "headcount" in out.columns:
        base["w"] = pd.to_numeric(out["headcount"], errors="coerce").fillna(0.0)
    else:
        base["w"] = pd.to_numeric(base["revenue"], errors="coerce").fillna(0.0)

    tot = base.groupby(["tenant_id", "farm_id", "date"], dropna=False)["w"].sum().reset_index().rename(columns={"w": "w_total"})
    base = base.merge(tot, on=["tenant_id", "farm_id", "date"], how="left")
    base["share"] = 0.0
    mask = base["w_total"] > 0
    base.loc[mask, "share"] = base.loc[mask, "w"] / base.loc[mask, "w_total"]
    # if total weight is 0 -> equal share across pens in that farm-day
    counts = base.groupby(["tenant_id", "farm_id", "date"], dropna=False)["pen_id"].nunique().reset_index().rename(columns={"pen_id": "n_pens"})
    base = base.merge(counts, on=["tenant_id", "farm_id", "date"], how="left")
    base.loc[~mask, "share"] = 1.0 / base.loc[~mask, "n_pens"].clip(lower=1)

    farm_other = farm_day[["tenant_id", "farm_id", "date", "other_cost"]].copy()
    base = base.merge(farm_other, on=["tenant_id", "farm_id", "date"], how="left")
    base["other_cost"] = pd.to_numeric(base["other_cost"], errors="coerce").fillna(0.0) * base["share"]
    out = out.merge(base[["tenant_id", "farm_id", "date", "pen_id", "other_cost"]], on=["tenant_id", "farm_id", "date", "pen_id"], how="left")
    out["other_cost"] = pd.to_numeric(out["other_cost"], errors="coerce").fillna(0.0)
    return out


def _build_margins(
    *,
    prices_farm_day: pd.DataFrame,
    milk_pen_day: pd.DataFrame,
    feed_pen_day: pd.DataFrame,
    cfg: Dict[str, Any],
    milk_mult: float,
    feed_mult: float,
    other_mult: float,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (farm_day, pen_day) for a given scenario multipliers."""
    alloc = (cfg or {}).get("allocation", {})
    alloc_method = str(alloc.get("other_cost_allocation", "revenue_share"))

    pf = prices_farm_day.copy()
    pf["milk_price_per_kg"] = pd.to_numeric(pf["milk_price_per_kg"], errors="coerce").fillna(0.0) * float(milk_mult)
    pf["feed_cost_per_kg_dm"] = pd.to_numeric(pf["feed_cost_per_kg_dm"], errors="coerce").fillna(0.0) * float(feed_mult)
    pf["other_cost"] = pd.to_numeric(pf["other_cost"], errors="coerce").fillna(0.0) * float(other_mult)

    # pen_day: join milk and feed
    pen = pd.merge(
        milk_pen_day,
        feed_pen_day,
        on=["tenant_id", "farm_id", "pen_id", "pen_type", "date"],
        how="outer",
    )
    if pen.empty:
        pen = pd.DataFrame(columns=["tenant_id","farm_id","pen_id","pen_type","date","milk_kg","feed_dm_kg"])
    pen["milk_kg"] = pd.to_numeric(pen.get("milk_kg"), errors="coerce").fillna(0.0)
    pen["feed_dm_kg"] = pd.to_numeric(pen.get("feed_dm_kg"), errors="coerce").fillna(0.0)

    pen = pen.merge(pf, on=["tenant_id", "farm_id", "date"], how="left")
    # pen-level other_cost будет рассчитан отдельным шагом распределения,
    # поэтому не держим farm-level колонку other_cost чтобы избежать suffix '_x/_y'.
    if "other_cost" in pen.columns:
        pen.drop(columns=["other_cost"], inplace=True)
    pen["revenue"] = pen["milk_kg"] * pd.to_numeric(pen.get("milk_price_per_kg"), errors="coerce").fillna(0.0)
    pen["feed_cost"] = pen["feed_dm_kg"] * pd.to_numeric(pen.get("feed_cost_per_kg_dm"), errors="coerce").fillna(0.0)

    pen = _allocate_other_cost_to_pens(pen_day=pen, farm_day=pf, method=alloc_method)
    pen["total_cost"] = pen["feed_cost"] + pen["other_cost"]
    pen["margin"] = pen["revenue"] - pen["total_cost"]
    pen["margin_pct"] = 0.0
    mask = pen["revenue"] > 0
    pen.loc[mask, "margin_pct"] = pen.loc[mask, "margin"] / pen.loc[mask, "revenue"]

    # farm_day from pen aggregates
    farm = pen.groupby(["tenant_id", "farm_id", "date"], dropna=False).agg(
        milk_kg=("milk_kg", "sum"),
        revenue=("revenue", "sum"),
        feed_dm_kg=("feed_dm_kg", "sum"),
        feed_cost=("feed_cost", "sum"),
        other_cost=("other_cost", "sum"),
        total_cost=("total_cost", "sum"),
        margin=("margin", "sum"),
    ).reset_index()
    farm = farm.merge(pf[["tenant_id","farm_id","date","milk_price_per_kg","feed_cost_per_kg_dm"]], on=["tenant_id","farm_id","date"], how="left")
    farm["margin_pct"] = 0.0
    mask = farm["revenue"] > 0
    farm.loc[mask, "margin_pct"] = farm.loc[mask, "margin"] / farm.loc[mask, "revenue"]

    # stable column order
    farm_cols = [
        "tenant_id","farm_id","date","milk_kg","milk_price_per_kg","revenue","feed_dm_kg","feed_cost_per_kg_dm","feed_cost","other_cost","total_cost","margin","margin_pct"
    ]
    pen_cols = [
        "tenant_id","farm_id","pen_id","pen_type","date","milk_kg","milk_price_per_kg","revenue","feed_dm_kg","feed_cost_per_kg_dm","feed_cost","other_cost","total_cost","margin","margin_pct"
    ]
    farm = farm[[c for c in farm_cols if c in farm.columns]]
    pen = pen[[c for c in pen_cols if c in pen.columns]]
    return farm, pen


def _write_xlsx(path: Path, sheets: Dict[str, pd.DataFrame]) -> None:
    try:
        with pd.ExcelWriter(path, engine="openpyxl") as xw:
            for name, df in sheets.items():
                df.to_excel(xw, sheet_name=name[:31], index=False)
    except Exception:
        # best-effort: xlsx is optional
        pass


def run_economics_whatif(
    *,
    artifacts_root: Path,
    data_version: str,
    date_from: str,
    date_to: str,
    milk_price_multiplier: float = 1.0,
    feed_cost_multiplier: float = 1.0,
    other_cost_multiplier: float = 1.0,
    cfg_path: Path = DEFAULT_CFG_PATH,
    economics_run: Optional[str] = None,
    input_dir: Optional[Path] = None,
    tenant_id: str = "default",
) -> Dict[str, Any]:
    """Compute economics marts and what-if scenario.

    Returns dict with ok + economics_run.
    """
    artifacts_root = Path(artifacts_root)
    cfg = _load_cfg(cfg_path)

    d1, d2 = _date_range(date_from, date_to)
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

    # sanity: some fixtures may have dm_testday instead of dm_milkings_daily
    if milkings.empty:
        td = _read_table(canonical, "dm_testday")
        if not td.empty and {"animal_id","date","milk_kg"}.issubset(set(td.columns)):
            milkings = td[["tenant_id","animal_id","date","milk_kg"]].copy() if "tenant_id" in td.columns else td[["animal_id","date","milk_kg"]].assign(tenant_id=tenant_id)

    # parse dates in inputs to avoid merge_asof dtype issues
    for df, col in [
        (milkings, "date"),
        (deliveries, "delivery_date"),
        (pen_moves, "move_date"),
        (econ_daily, "date"),
        (prices, "valid_from"),
    ]:
        if not df.empty and col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    prices_farm_day = _build_prices_farm_day(
        econ_daily=econ_daily,
        prices=prices,
        farms=farms,
        date_from=d1,
        date_to=d2,
        cfg=cfg,
    )

    milk_pen_day = _build_milk_pen_day(
        milkings=milkings,
        animals=animals,
        pen_moves=pen_moves,
        pens=pens,
        sites=sites,
        date_from=d1,
        date_to=d2,
    )
    feed_pen_day = _build_feed_pen_day(
        deliveries=deliveries,
        rations=rations,
        pens=pens,
        sites=sites,
        date_from=d1,
        date_to=d2,
    )

    # baseline (multipliers = 1)
    farm_b, pen_b = _build_margins(
        prices_farm_day=prices_farm_day,
        milk_pen_day=milk_pen_day,
        feed_pen_day=feed_pen_day,
        cfg=cfg,
        milk_mult=1.0,
        feed_mult=1.0,
        other_mult=1.0,
    )
    farm_s, pen_s = _build_margins(
        prices_farm_day=prices_farm_day,
        milk_pen_day=milk_pen_day,
        feed_pen_day=feed_pen_day,
        cfg=cfg,
        milk_mult=milk_price_multiplier,
        feed_mult=feed_cost_multiplier,
        other_mult=other_cost_multiplier,
    )

    # summaries
    def _summ(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=keys + ["revenue","total_cost","margin","margin_pct"])
        agg = df.groupby(keys, dropna=False).agg(
            days=("date", "nunique"),
            revenue=("revenue", "sum"),
            total_cost=("total_cost", "sum"),
            margin=("margin", "sum"),
        ).reset_index()
        agg["margin_pct"] = 0.0
        mask2 = agg["revenue"] > 0
        agg.loc[mask2, "margin_pct"] = agg.loc[mask2, "margin"] / agg.loc[mask2, "revenue"]
        return agg

    sum_farm_b = _summ(farm_b, ["tenant_id","farm_id"])
    sum_pen_b = _summ(pen_b, ["tenant_id","farm_id","pen_id","pen_type"])
    sum_farm_s = _summ(farm_s, ["tenant_id","farm_id"])
    sum_pen_s = _summ(pen_s, ["tenant_id","farm_id","pen_id","pen_type"])

    # join baseline vs scenario in one summary for UI
    sum_farm = sum_farm_b.merge(sum_farm_s, on=["tenant_id","farm_id"], suffixes=("_baseline","_scenario"), how="outer")
    sum_pen = sum_pen_b.merge(sum_pen_s, on=["tenant_id","farm_id","pen_id","pen_type"], suffixes=("_baseline","_scenario"), how="outer")

    rid = economics_run or generate_run_id(prefix="econ")
    run_dir = artifacts_root / data_version / "economics" / rid
    run_dir.mkdir(parents=True, exist_ok=True)

    # write artifacts
    farm_b.to_csv(run_dir / "farm_day_baseline.csv", index=False)
    pen_b.to_csv(run_dir / "pen_day_baseline.csv", index=False)
    farm_s.to_csv(run_dir / "farm_day_scenario.csv", index=False)
    pen_s.to_csv(run_dir / "pen_day_scenario.csv", index=False)
    sum_farm.to_csv(run_dir / "summary_farm.csv", index=False)
    sum_pen.to_csv(run_dir / "summary_pen.csv", index=False)

    params = {
        "schema": "genomeai.economics.whatif_params.v1",
        "tenant_id": tenant_id,
        "data_version": data_version,
        "economics_run": rid,
        "date_from": str(d1.date()),
        "date_to": str(d2.date()),
        "milk_price_multiplier": float(milk_price_multiplier),
        "feed_cost_multiplier": float(feed_cost_multiplier),
        "other_cost_multiplier": float(other_cost_multiplier),
        "cfg_path": str(cfg_path),
        "created_at": _utc_ts(),
    }
    write_json(run_dir / "whatif_params.json", params)

    manifest = {
        "schema": "genomeai.economics.manifest.v1",
        "created_at": _utc_ts(),
        "tenant_id": tenant_id,
        "data_version": data_version,
        "economics_run": rid,
        "inputs": {
            "canonical_dir": str(canonical),
            "datasets": {
                "dm_milkings_daily": (canonical / "dm_milkings_daily.csv").name,
                "dm_feed_deliveries": (canonical / "dm_feed_deliveries.csv").name,
                "dm_feed_rations": (canonical / "dm_feed_rations.csv").name,
                "dm_economics_daily": (canonical / "dm_economics_daily.csv").name,
                "dm_prices": (canonical / "dm_prices.csv").name,
            },
        },
        "versions": {
            "data_version": data_version,
            "qc_run": None,
            "model_version": None,
            "scoring_run": None,
            "report_version": rid,
            "decision_log": None,
        },
        "limitations": [
            "Если отсутствуют dm_prices/dm_economics_daily, используются fallback цены из configs/economics/economics_v1.yaml.",
            "Прочие затраты распределяются по группам по правилу allocation.other_cost_allocation.",
        ],
    }
    write_json(run_dir / "manifest.json", manifest)

    # xlsx (best-effort)
    _write_xlsx(
        run_dir / "economics_whatif.xlsx",
        {
            "farm_day_baseline": farm_b,
            "farm_day_scenario": farm_s,
            "summary_farm": sum_farm,
            "pen_day_baseline": pen_b,
            "pen_day_scenario": pen_s,
            "summary_pen": sum_pen,
            "params": pd.DataFrame([params]),
        },
    )
    write_checksums(run_root=run_dir)

    return {
        "ok": True,
        "economics_run": rid,
        "data_version": data_version,
        "run_dir": str(run_dir),
    }


def load_economics(
    *,
    artifacts_root: Path,
    data_version: str,
    economics_run: Optional[str] = None,
) -> Tuple[str, Dict[str, pd.DataFrame]]:
    root = Path(artifacts_root) / data_version / "economics"
    run_dir = root / economics_run if economics_run else _latest_run_dir(root)
    if run_dir is None or not run_dir.exists():
        raise FileNotFoundError("Нет arifacts economics run")
    rid = run_dir.name

    def _rd(name: str) -> pd.DataFrame:
        p = run_dir / name
        return pd.read_csv(p) if p.exists() else pd.DataFrame()

    dfs = {
        "farm_day_baseline": _rd("farm_day_baseline.csv"),
        "farm_day_scenario": _rd("farm_day_scenario.csv"),
        "summary_farm": _rd("summary_farm.csv"),
        "pen_day_baseline": _rd("pen_day_baseline.csv"),
        "pen_day_scenario": _rd("pen_day_scenario.csv"),
        "summary_pen": _rd("summary_pen.csv"),
    }
    return rid, dfs


def _totals_from_summary_farm(sum_farm: "pd.DataFrame") -> dict[str, float]:
    """Compute total revenue/cost/margin from summary_farm.

    Designed for What-If comparison use-cases where UI must not "calculate".
    """
    import pandas as pd

    if sum_farm is None or getattr(sum_farm, "empty", True):
        return {"revenue": 0.0, "total_cost": 0.0, "margin": 0.0, "margin_pct": 0.0}

    df = sum_farm
    # Prefer *_scenario columns (they exist for run_economics_whatif outputs)
    def pick(*names: str) -> str | None:
        for n in names:
            if n in df.columns:
                return n
        return None

    c_rev = pick("revenue_scenario", "revenue")
    c_cost = pick("total_cost_scenario", "total_cost")
    c_margin = pick("margin_scenario", "margin")
    if not c_rev or not c_cost or not c_margin:
        return {"revenue": 0.0, "total_cost": 0.0, "margin": 0.0, "margin_pct": 0.0}

    revenue = float(pd.to_numeric(df[c_rev], errors="coerce").fillna(0.0).sum())
    total_cost = float(pd.to_numeric(df[c_cost], errors="coerce").fillna(0.0).sum())
    margin = float(pd.to_numeric(df[c_margin], errors="coerce").fillna(0.0).sum())
    margin_pct = (margin / revenue) if revenue > 0 else 0.0
    return {"revenue": revenue, "total_cost": total_cost, "margin": margin, "margin_pct": float(margin_pct)}


def compare_whatif_scenarios(
    *,
    artifacts_root: Path,
    data_version: str,
    date_from: str,
    date_to: str,
    cfg_path: Path = DEFAULT_CFG_PATH,
    scenarios: list[dict[str, Any]] | None = None,
    input_dir: Optional[Path] = None,
    tenant_id: str = "default",
) -> dict[str, Any]:
    """Run and compare up to 3 what-if scenarios against baseline.

    Each scenario item is expected to contain:
      - name (str)
      - milk_price_multiplier (float)
      - feed_cost_multiplier (float)
      - other_cost_multiplier (float)

    Returns:
      - base_economics_run
      - scenario_runs: {name: economics_run}
      - comparison: list[dict] with totals and deltas vs base.
    """
    scenarios = list(scenarios or [])
    if len(scenarios) > 3:
        raise ValueError("Слишком много сценариев для сравнения: максимум 3")

    # base run (multipliers=1)
    base_res = run_economics_whatif(
        artifacts_root=artifacts_root,
        data_version=data_version,
        date_from=date_from,
        date_to=date_to,
        milk_price_multiplier=1.0,
        feed_cost_multiplier=1.0,
        other_cost_multiplier=1.0,
        cfg_path=cfg_path,
        input_dir=input_dir,
        tenant_id=tenant_id,
    )
    if not base_res.get("ok"):
        return {"ok": False, "reason": "base_run_failed"}
    base_run = str(base_res.get("economics_run") or "")
    _, base_dfs = load_economics(artifacts_root=artifacts_root, data_version=data_version, economics_run=base_run)
    base_tot = _totals_from_summary_farm(base_dfs.get("summary_farm"))

    comparison: list[dict[str, Any]] = []
    comparison.append(
        {
            "scenario": "BASE",
            "economics_run": base_run,
            **base_tot,
            "revenue_delta": 0.0,
            "total_cost_delta": 0.0,
            "margin_delta": 0.0,
            "margin_pct_delta": 0.0,
        }
    )

    scenario_runs: dict[str, str] = {}
    for s in scenarios:
        name = str(s.get("name") or "").strip() or "scenario"
        milk = float(s.get("milk_price_multiplier") or 1.0)
        feed = float(s.get("feed_cost_multiplier") or 1.0)
        other = float(s.get("other_cost_multiplier") or 1.0)

        res = run_economics_whatif(
            artifacts_root=artifacts_root,
            data_version=data_version,
            date_from=date_from,
            date_to=date_to,
            milk_price_multiplier=milk,
            feed_cost_multiplier=feed,
            other_cost_multiplier=other,
            cfg_path=cfg_path,
            input_dir=input_dir,
            tenant_id=tenant_id,
        )
        if not res.get("ok"):
            raise RuntimeError(f"Не удалось посчитать экономику для сценария '{name}'")
        rid = str(res.get("economics_run") or "")
        scenario_runs[name] = rid
        _, dfs = load_economics(artifacts_root=artifacts_root, data_version=data_version, economics_run=rid)
        tot = _totals_from_summary_farm(dfs.get("summary_farm"))

        comparison.append(
            {
                "scenario": name,
                "economics_run": rid,
                **tot,
                "revenue_delta": float(tot["revenue"] - base_tot["revenue"]),
                "total_cost_delta": float(tot["total_cost"] - base_tot["total_cost"]),
                "margin_delta": float(tot["margin"] - base_tot["margin"]),
                "margin_pct_delta": float(tot["margin_pct"] - base_tot["margin_pct"]),
            }
        )

    return {
        "ok": True,
        "base_economics_run": base_run,
        "scenario_runs": scenario_runs,
        "comparison": comparison,
        "data_version": data_version,
    }

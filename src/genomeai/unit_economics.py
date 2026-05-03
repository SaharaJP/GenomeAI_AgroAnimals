from __future__ import annotations

"""T11-03 (step 1): Unit economics — вклад животного/группы в прибыль.

Первый инкремент:
- Считаем витрины unit_economics_animal_daily и unit_economics_group_daily.
- Берём pen-day экономику из economics_v2 (offline-core уже считает прозрачные формулы и refdata overrides).
- Декомпозиция:
  * milk revenue + feed/other costs: распределяем по animals через milk_share (или headcount — позже).
  * vet/repro/cull: атрибутируем напрямую к животным через события (dm_treatments, dm_repro_events, dm_cull_events).

Важно:
- Это attribution/allocations, а не доказанная причинность.
- UI ничего не считает: только запускает этот модуль и читает артефакты.

Выходы:
  artifacts/<data_version>/unit_economics/<unit_econ_run>/
    - unit_economics_animal_daily.csv
    - unit_economics_group_daily.csv
    - manifest.json

И дополнительно Target run layout:
  artifacts/<data_version>/runs/<unit_econ_run>/unit_economics/

"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from .economics_v2 import load_economics_v2
from .versioning import generate_run_id, ensure_run_dir, write_json, write_run_manifest, write_checksums

DEFAULT_CFG_PATH = Path("configs/economics/unit_economics_v1.yaml")


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


def _parse_date(df: pd.DataFrame, col: str) -> None:
    if df.empty or col not in df.columns:
        return
    df[col] = pd.to_datetime(df[col], errors="coerce").dt.normalize()


def _assign_pen_on_date(records: pd.DataFrame, animals: pd.DataFrame, pen_moves: pd.DataFrame) -> pd.DataFrame:
    """Assign pen_id to each record using latest move <= date, fallback to animals.current_pen_id."""
    out = records.copy()
    if out.empty:
        out["pen_id"] = None
        return out

    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()

    # baseline: animal -> current_pen_id, farm_id, site_id
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
    if "move_date" in pm.columns:
        pm["move_date"] = pd.to_datetime(pm["move_date"], errors="coerce").dt.normalize()

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
    merged["pen_id"] = merged["pen_id_move"].fillna(merged["pen_id"])
    return merged.drop(columns=[c for c in ["move_date", "pen_id_move"] if c in merged.columns])


def _read_cost_models_from_econ_run(econ_run_dir: Path) -> Dict[str, float]:
    """Best-effort read cost model params from economics_v2 formulas_catalog.json."""
    p = econ_run_dir / "formulas_catalog.json"
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    params = (obj or {}).get("cost_models") or {}
    out: Dict[str, float] = {}
    for k in [
        "vet_cost_per_treatment_event_rub",
        "insemination_cost_rub",
    ]:
        try:
            out[k] = float(params.get(k) or 0.0)
        except Exception:
            out[k] = 0.0
    return out


def run_unit_economics(
    *,
    artifacts_root: Path,
    data_version: str,
    cfg_path: Path = DEFAULT_CFG_PATH,
    unit_econ_run: Optional[str] = None,
    economics_run: Optional[str] = None,
    input_dir: Optional[Path] = None,
    tenant_id: str = "default",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute unit economics marts for animals and groups.

    Requires existing economics_v2 run for the same data_version.
    """

    artifacts_root = Path(artifacts_root)
    cfg = _load_cfg(Path(cfg_path))
    alloc = (cfg.get("allocation") or {})
    cost_method = str(alloc.get("cost_method") or "milk_share")
    eps_total = float(alloc.get("eps_total") or 1.0e-9)
    if_zero_total_milk = str(alloc.get("if_zero_total_milk") or "skip")

    if cost_method not in {"milk_share", "headcount"}:
        raise ValueError(f"allocation.cost_method должен быть milk_share или headcount (получено: {cost_method})")

    # Load economics_v2 (pen-day) as the source of truth for pen-level totals
    econ_rid, econ_dfs, econ_run_dir = load_economics_v2(
        artifacts_root=artifacts_root,
        data_version=data_version,
        economics_run=economics_run,
    )
    econ_daily = econ_dfs.get("economics_daily", pd.DataFrame())
    if econ_daily.empty:
        raise ValueError("economics_v2.economics_daily пуст — пересчитайте economics_v2")

    # filter to pen rows
    if "level" in econ_daily.columns:
        econ_pen = econ_daily[econ_daily["level"].astype(str) == "pen"].copy()
    else:
        econ_pen = econ_daily.copy()

    if econ_pen.empty:
        raise ValueError("economics_v2 не содержит level=pen — не можем атрибутировать на животных")

    if "date" not in econ_pen.columns:
        raise ValueError("economics_daily не содержит колонку date")

    econ_pen["date"] = pd.to_datetime(econ_pen["date"], errors="coerce").dt.normalize()
    econ_pen = econ_pen.dropna(subset=["date"])

    # infer date window from econ run if not provided
    dmin = econ_pen["date"].min()
    dmax = econ_pen["date"].max()
    d1 = pd.to_datetime(date_from).normalize() if date_from else dmin
    d2 = pd.to_datetime(date_to).normalize() if date_to else dmax
    if pd.isna(d1) or pd.isna(d2):
        raise ValueError("Неверные даты date_from/date_to")
    if d2 < d1:
        raise ValueError("date_to < date_from")

    econ_pen = econ_pen[(econ_pen["date"] >= d1) & (econ_pen["date"] <= d2)].copy()

    # Canonical inputs
    canonical = _resolve_canonical_dir(artifacts_root, data_version, input_dir=input_dir)
    animals = _read_table(canonical, "dm_animals")
    pen_moves = _read_table(canonical, "dm_pen_moves")
    milkings = _read_table(canonical, "dm_milkings_daily")
    treatments = _read_table(canonical, "dm_treatments")
    repro = _read_table(canonical, "dm_repro_events")
    cull = _read_table(canonical, "dm_cull_events")

    # fixtures fallback
    if milkings.empty:
        td = _read_table(canonical, "dm_testday")
        if not td.empty and {"animal_id", "date", "milk_kg"}.issubset(set(td.columns)):
            base = td[["animal_id", "date", "milk_kg"]].copy()
            base["tenant_id"] = tenant_id
            milkings = base

    # Parse dates
    for df, col in [
        (milkings, "date"),
        (treatments, "start_date"),
        (repro, "event_date"),
        (cull, "event_date"),
        (pen_moves, "move_date"),
    ]:
        if not df.empty and col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    # --- animal-day base set (milkings + event-days) + pen assignment ---
    if milkings.empty or not {"animal_id", "date", "milk_kg"}.issubset(set(milkings.columns)):
        raise ValueError(
            "Не найден dm_milkings_daily (или нет колонок animal_id/date/milk_kg) — unit economics v1 требует удои"
        )

    m = milkings[[c for c in ["tenant_id", "animal_id", "date", "milk_kg"] if c in milkings.columns]].copy()
    if "tenant_id" not in m.columns:
        m["tenant_id"] = tenant_id
    m["date"] = pd.to_datetime(m["date"], errors="coerce").dt.normalize()
    m = m[(m["date"] >= d1) & (m["date"] <= d2)].copy()
    m["milk_kg"] = pd.to_numeric(m.get("milk_kg"), errors="coerce")
    m = m.dropna(subset=["tenant_id", "animal_id", "date"]).copy()
    m["milk_kg"] = m["milk_kg"].fillna(0.0)

    # Add animals that have events (treat/repro/cull) even if they have no milking record in the window.
    extra_parts = []
    def _evt_days(df, date_col: str) -> None:
        if df is None or df.empty:
            return
        if date_col not in df.columns or "animal_id" not in df.columns:
            return
        x = df.copy()
        if "tenant_id" not in x.columns:
            x["tenant_id"] = tenant_id
        x["date"] = pd.to_datetime(x[date_col], errors="coerce").dt.normalize()
        x = x[(x["date"] >= d1) & (x["date"] <= d2)].dropna(subset=["tenant_id", "animal_id", "date"])
        if x.empty:
            return
        y = x[["tenant_id", "animal_id", "date"]].drop_duplicates().copy()
        y["milk_kg"] = 0.0
        extra_parts.append(y)

    _evt_days(treatments, "start_date")
    _evt_days(repro, "event_date")
    _evt_days(cull, "event_date")

    if extra_parts:
        m = pd.concat([m] + extra_parts, ignore_index=True)
        m = m.groupby(["tenant_id", "animal_id", "date"], dropna=False, as_index=False).agg({"milk_kg": "sum"})

    assigned = _assign_pen_on_date(m, animals, pen_moves)

    # sanity: need pen_id for join
    if "pen_id" not in assigned.columns:
        assigned["pen_id"] = pd.NA

    # pen/day totals
    pen_tot = (
        assigned.groupby(["tenant_id", "pen_id", "date"], dropna=False)["milk_kg"].sum().reset_index().rename(columns={"milk_kg": "pen_milk_kg"})
    )
    assigned = assigned.merge(pen_tot, on=["tenant_id", "pen_id", "date"], how="left")
    assigned["pen_milk_kg"] = pd.to_numeric(assigned.get("pen_milk_kg"), errors="coerce").fillna(0.0)

    # compute share
    if cost_method == "milk_share":
        denom = assigned["pen_milk_kg"].clip(lower=0.0)
        assigned["share"] = 0.0
        ok = denom > eps_total
        assigned.loc[ok, "share"] = (assigned.loc[ok, "milk_kg"] / denom.loc[ok]).astype(float)
        if if_zero_total_milk != "skip":
            # future extension
            pass
    else:
        # headcount: count animals per pen/day in milkings (v1 approximation)
        cnt = assigned.groupby(["tenant_id", "pen_id", "date"], dropna=False)["animal_id"].nunique().reset_index().rename(columns={"animal_id": "pen_animals_n"})
        assigned = assigned.merge(cnt, on=["tenant_id", "pen_id", "date"], how="left")
        assigned["pen_animals_n"] = pd.to_numeric(assigned.get("pen_animals_n"), errors="coerce").fillna(0.0)
        assigned["share"] = 0.0
        ok = assigned["pen_animals_n"] > 0
        assigned.loc[ok, "share"] = (1.0 / assigned.loc[ok, "pen_animals_n"].astype(float)).astype(float)

    # --- join pen-day economics (from economics_v2) ---
    need_cols = [
        "tenant_id",
        "pen_id",
        "date",
        "farm_id",
        "site_id",
        "revenue_milk_rub",
        "revenue_cull_rub",
        "cost_feed_rub",
        "cost_other_rub",
        "cost_vet_rub",
        "cost_repro_rub",
        "cost_cull_rub",
        "total_cost_rub",
        "revenue_total_rub",
        "margin_rub",
    ]
    for c in need_cols:
        if c not in econ_pen.columns:
            econ_pen[c] = 0.0 if c not in {"tenant_id", "pen_id", "date", "farm_id", "site_id"} else pd.NA

    econ_pen2 = econ_pen[[c for c in need_cols if c in econ_pen.columns]].copy()
    if "tenant_id" not in econ_pen2.columns:
        econ_pen2["tenant_id"] = tenant_id

    merged = assigned.merge(
        econ_pen2,
        on=["tenant_id", "pen_id", "date"],
        how="left",
        suffixes=("", "_pen"),
    )

    # If join fails (no econ row), make it explicit
    miss = merged[merged["revenue_total_rub"].isna()]
    if not miss.empty:
        ex = miss.head(1).iloc[0]
        raise ValueError(
            "Нет economics_v2 pen-day строки для animal-day. "
            f"Пример: tenant_id={ex.get('tenant_id')} pen_id={ex.get('pen_id')} date={str(ex.get('date'))[:10]}. "
            "Пересчитайте economics_v2 на нужный диапазон дат."
        )

    # numeric cast
    for c in [
        "revenue_milk_rub",
        "revenue_cull_rub",
        "cost_feed_rub",
        "cost_other_rub",
        "cost_vet_rub",
        "cost_repro_rub",
        "cost_cull_rub",
    ]:
        merged[c] = pd.to_numeric(merged.get(c), errors="coerce").fillna(0.0)

    # allocate pen-level milk revenue + feed/other by share
    merged["revenue_milk_rub_alloc"] = merged["revenue_milk_rub"] * merged["share"].astype(float)
    merged["cost_feed_rub_alloc"] = merged["cost_feed_rub"] * merged["share"].astype(float)
    merged["cost_other_rub_alloc"] = merged["cost_other_rub"] * merged["share"].astype(float)

    # --- direct attribution for vet/repro/cull (events) ---
    params = _read_cost_models_from_econ_run(econ_run_dir)
    vet_cost = float(params.get("vet_cost_per_treatment_event_rub") or 0.0)
    repro_cost = float(params.get("insemination_cost_rub") or 0.0)
    cull_rev_def = float(params.get("cull_revenue_per_head_rub") or 0.0)
    cull_cost_def = float(params.get("cull_cost_per_head_rub") or 0.0)

    # treatments: start_date
    vet_df = pd.DataFrame(columns=["tenant_id", "animal_id", "date", "cost_vet_rub_direct"])
    if not treatments.empty and {"animal_id", "start_date"}.issubset(set(treatments.columns)):
        t = treatments.copy()
        if "tenant_id" not in t.columns:
            t["tenant_id"] = tenant_id
        t["date"] = pd.to_datetime(t["start_date"], errors="coerce").dt.normalize()
        t = t[(t["date"] >= d1) & (t["date"] <= d2)].dropna(subset=["tenant_id", "animal_id", "date"])
        if not t.empty:
            g = t.groupby(["tenant_id", "animal_id", "date"], dropna=False).size().reset_index(name="n")
            g["cost_vet_rub_direct"] = g["n"].astype(float) * vet_cost
            vet_df = g[["tenant_id", "animal_id", "date", "cost_vet_rub_direct"]].copy()

    # repro: insemination events
    repro_df = pd.DataFrame(columns=["tenant_id", "animal_id", "date", "cost_repro_rub_direct"])
    if not repro.empty and {"animal_id", "event_date"}.issubset(set(repro.columns)):
        r = repro.copy()
        if "tenant_id" not in r.columns:
            r["tenant_id"] = tenant_id
        r["date"] = pd.to_datetime(r["event_date"], errors="coerce").dt.normalize()
        if "event_type" in r.columns:
            r = r[r["event_type"].astype(str) == "insemination"]
        r = r[(r["date"] >= d1) & (r["date"] <= d2)].dropna(subset=["tenant_id", "animal_id", "date"])
        if not r.empty:
            g = r.groupby(["tenant_id", "animal_id", "date"], dropna=False).size().reset_index(name="n")
            g["cost_repro_rub_direct"] = g["n"].astype(float) * repro_cost
            repro_df = g[["tenant_id", "animal_id", "date", "cost_repro_rub_direct"]].copy()

    # cull: direct revenue/cost
    cull_df = pd.DataFrame(columns=["tenant_id", "animal_id", "date", "revenue_cull_rub_direct", "cost_cull_rub_direct"])
    if not cull.empty and {"animal_id", "event_date"}.issubset(set(cull.columns)):
        cu = cull.copy()
        if "tenant_id" not in cu.columns:
            cu["tenant_id"] = tenant_id
        cu["date"] = pd.to_datetime(cu["event_date"], errors="coerce").dt.normalize()
        cu = cu[(cu["date"] >= d1) & (cu["date"] <= d2)].dropna(subset=["tenant_id", "animal_id", "date"])
        if not cu.empty:
            if "revenue_rub" not in cu.columns:
                cu["revenue_rub"] = cull_rev_def
            cu["revenue_rub"] = pd.to_numeric(cu.get("revenue_rub"), errors="coerce").fillna(cull_rev_def)
            if "cost_rub" not in cu.columns:
                cu["cost_rub"] = cull_cost_def
            cu["cost_rub"] = pd.to_numeric(cu.get("cost_rub"), errors="coerce").fillna(cull_cost_def)
            g = cu.groupby(["tenant_id", "animal_id", "date"], dropna=False).agg({"revenue_rub": "sum", "cost_rub": "sum"}).reset_index()
            g.rename(columns={"revenue_rub": "revenue_cull_rub_direct", "cost_rub": "cost_cull_rub_direct"}, inplace=True)
            cull_df = g

    out = merged[[
        "tenant_id",
        "animal_id",
        "date",
        "farm_id",
        "site_id",
        "pen_id",
        "milk_kg",
        "share",
        "revenue_milk_rub_alloc",
        "cost_feed_rub_alloc",
        "cost_other_rub_alloc",
    ]].copy()

    # add direct components
    out = out.merge(vet_df, on=["tenant_id", "animal_id", "date"], how="left")
    out = out.merge(repro_df, on=["tenant_id", "animal_id", "date"], how="left")
    out = out.merge(cull_df, on=["tenant_id", "animal_id", "date"], how="left")

    for c in ["cost_vet_rub_direct", "cost_repro_rub_direct", "revenue_cull_rub_direct", "cost_cull_rub_direct"]:
        out[c] = pd.to_numeric(out.get(c), errors="coerce").fillna(0.0)

    out.rename(
        columns={
            "revenue_milk_rub_alloc": "revenue_milk_rub",
            "cost_feed_rub_alloc": "cost_feed_rub",
            "cost_other_rub_alloc": "cost_other_rub",
            "cost_vet_rub_direct": "cost_vet_rub",
            "cost_repro_rub_direct": "cost_repro_rub",
            "revenue_cull_rub_direct": "revenue_cull_rub",
            "cost_cull_rub_direct": "cost_cull_rub",
        },
        inplace=True,
    )

    out["revenue_total_rub"] = out["revenue_milk_rub"] + out["revenue_cull_rub"]
    out["total_cost_rub"] = out["cost_feed_rub"] + out["cost_other_rub"] + out["cost_vet_rub"] + out["cost_repro_rub"] + out["cost_cull_rub"]
    out["margin_rub"] = out["revenue_total_rub"] - out["total_cost_rub"]

    out["economics_run"] = str(econ_rid)

    # --- group daily aggregates (pen/site/farm) ---
    def _agg(level: str, keys: list[str]) -> pd.DataFrame:
        g = out.groupby(keys + ["date"], dropna=False).agg(
            {
                "milk_kg": "sum",
                "revenue_milk_rub": "sum",
                "revenue_cull_rub": "sum",
                "revenue_total_rub": "sum",
                "cost_feed_rub": "sum",
                "cost_other_rub": "sum",
                "cost_vet_rub": "sum",
                "cost_repro_rub": "sum",
                "cost_cull_rub": "sum",
                "total_cost_rub": "sum",
                "margin_rub": "sum",
            }
        ).reset_index()
        g["level"] = level
        return g

    g_pen = _agg("pen", ["tenant_id", "farm_id", "site_id", "pen_id"])
    g_site = _agg("site", ["tenant_id", "farm_id", "site_id"])
    g_farm = _agg("farm", ["tenant_id", "farm_id"])

    group_daily = pd.concat([g_pen, g_site, g_farm], ignore_index=True)
    group_daily["economics_run"] = str(econ_rid)

    # --- write outputs ---
    rid = unit_econ_run or generate_run_id(prefix="uec")
    root = artifacts_root / data_version / "unit_economics"
    run_dir = root / str(rid)
    run_dir.mkdir(parents=True, exist_ok=True)

    out.sort_values(["date", "animal_id"], inplace=True)
    group_daily.sort_values(["date", "level"], inplace=True)

    out.to_csv(run_dir / "unit_economics_animal_daily.csv", index=False)
    group_daily.to_csv(run_dir / "unit_economics_group_daily.csv", index=False)

    manifest = {
        "schema": "genomeai.unit_economics.manifest.v1",
        "created_at": _utc_ts(),
        "tenant_id": tenant_id,
        "data_version": data_version,
        "unit_econ_run": rid,
        "economics_run": str(econ_rid),
        "cfg_path": str(Path(cfg_path)),
        "date_from": str(pd.to_datetime(d1).date()),
        "date_to": str(pd.to_datetime(d2).date()),
        "allocation": {
            "cost_method": cost_method,
            "if_zero_total_milk": if_zero_total_milk,
        },
        "cost_models": {
            "vet_cost_per_treatment_event_rub": vet_cost,
            "insemination_cost_rub": repro_cost,
        },
        "limitations": (cfg.get("limitations") or []),
    }
    write_json(run_dir / "manifest.json", manifest)

    # Target run layout
    run_root = ensure_run_dir(artifacts_root, data_version, rid)
    out_sub = run_root / "unit_economics"
    out_sub.mkdir(parents=True, exist_ok=True)
    for name in ["unit_economics_animal_daily.csv", "unit_economics_group_daily.csv", "manifest.json"]:
        p = run_dir / name
        if p.exists():
            (out_sub / name).write_bytes(p.read_bytes())

    run_manifest = {
        "schema": "genomeai.run_manifest.v1",
        "step": "unit_economics",
        "data_version": data_version,
        "run_id": rid,
        "created_at": manifest["created_at"],
        "status": "DONE",
        "outputs": {
            "legacy_dir": str(run_dir.resolve()),
            "run_dir": str(out_sub.resolve()),
            "unit_economics_animal_daily": str((out_sub / "unit_economics_animal_daily.csv").resolve()),
            "unit_economics_group_daily": str((out_sub / "unit_economics_group_daily.csv").resolve()),
        },
        "params": {
            "economics_run": str(econ_rid),
            "date_from": manifest["date_from"],
            "date_to": manifest["date_to"],
            "allocation.cost_method": cost_method,
        },
    }
    write_run_manifest(run_root=run_root, manifest=run_manifest)
    write_checksums(run_root=run_root, include_subdirs=["unit_economics"])

    # per-data_version metadata manifest
    meta_dir = Path(artifacts_root) / data_version / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta_path = meta_dir / "unit_economics_manifest.json"
    if meta_path.exists():
        try:
            mobj = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            mobj = {}
    else:
        mobj = {"schema": "genomeai.unit_economics_manifest.v1", "data_version": data_version, "runs": {}, "latest": None}

    mobj.setdefault("runs", {})
    mobj["runs"][rid] = {
        "created_at": manifest["created_at"],
        "economics_run": str(econ_rid),
        "date_from": manifest["date_from"],
        "date_to": manifest["date_to"],
        "allocation": manifest["allocation"],
    }
    mobj["latest"] = rid
    write_json(meta_path, mobj)

    return {
        "ok": True,
        "unit_econ_run": rid,
        "economics_run": str(econ_rid),
        "run_dir": str(run_dir.resolve()),
        "outputs": {
            "unit_economics_animal_daily": str((run_dir / "unit_economics_animal_daily.csv").resolve()),
            "unit_economics_group_daily": str((run_dir / "unit_economics_group_daily.csv").resolve()),
        },
    }


def list_unit_economics_runs(*, artifacts_root: Path, data_version: str) -> list[str]:
    root = Path(artifacts_root) / data_version / "unit_economics"
    if not root.exists():
        return []
    dirs = [p.name for p in root.iterdir() if p.is_dir()]
    # prefer metadata order
    meta_path = Path(artifacts_root) / data_version / "metadata" / "unit_economics_manifest.json"
    if meta_path.exists():
        try:
            obj = json.loads(meta_path.read_text(encoding="utf-8"))
            runs = list((obj or {}).get("runs", {}).keys())
            # keep only existing
            runs = [r for r in runs if (root / r).exists()]
            if runs:
                return runs
        except Exception:
            pass
    return sorted(dirs)


def load_unit_economics(
    *,
    artifacts_root: Path,
    data_version: str,
    unit_econ_run: Optional[str] = None,
) -> Tuple[str, Dict[str, pd.DataFrame], Path]:
    root = Path(artifacts_root) / data_version / "unit_economics"

    rid: Optional[str] = unit_econ_run
    if rid is None:
        meta_path = Path(artifacts_root) / data_version / "metadata" / "unit_economics_manifest.json"
        if meta_path.exists():
            try:
                obj = json.loads(meta_path.read_text(encoding="utf-8"))
                rid = (obj or {}).get("latest")
            except Exception:
                rid = None

    if rid is None:
        if not root.exists():
            raise FileNotFoundError("Нет unit_economics запусков")
        dirs = [p for p in root.iterdir() if p.is_dir()]
        if not dirs:
            raise FileNotFoundError("Нет unit_economics запусков")
        dirs = sorted(dirs, key=lambda p: p.stat().st_mtime, reverse=True)
        rid = dirs[0].name

    run_dir = root / str(rid)
    if not run_dir.exists():
        raise FileNotFoundError(f"Нет unit_economics run: {rid}")

    def _rd_csv(name: str) -> pd.DataFrame:
        p = run_dir / name
        return pd.read_csv(p) if p.exists() else pd.DataFrame()

    dfs = {
        "animal_daily": _rd_csv("unit_economics_animal_daily.csv"),
        "group_daily": _rd_csv("unit_economics_group_daily.csv"),
    }
    return str(rid), dfs, run_dir

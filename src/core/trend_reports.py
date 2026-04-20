from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from core.list_builder import _build_events_df, _join_pen_assignments, _read_csv, _role_key

TREND_REPORT_TYPES: tuple[str, ...] = (
    "milk_output_trend",
    "health_events_trend",
    "repro_events_trend",
    "milk_quality_trend",
    "dim_milk_curve",
)

TREND_COMPARE_MODES: tuple[str, ...] = ("none", "period", "site", "group")
TREND_GRAINS: tuple[str, ...] = ("day", "week")


TREND_REPORT_DEFS: dict[str, dict[str, Any]] = {
    "milk_output_trend": {
        "label": "Milk output trend",
        "description": "Operational milk trend by day/week from pre-aggregated daily milk records.",
        "chart_kind": "line",
        "drilldown_object_type": "animals",
        "default_days": 30,
        "default_grain": "day",
        "formula_rows": (
            {"metric": "value", "formula": "avg(milk_kg) by bucket over filtered records"},
            {"metric": "compare.period", "formula": "previous contiguous period with same length, aligned by bucket index"},
            {"metric": "compare.site/group", "formula": "same current period, same bucket boundaries, split by selected site_id or pen_id"},
        ),
    },
    "health_events_trend": {
        "label": "Health events trend",
        "description": "Count of health events by day/week with compare-period and site/group split where available.",
        "chart_kind": "bar",
        "drilldown_object_type": "events",
        "default_days": 30,
        "default_grain": "day",
        "formula_rows": (
            {"metric": "value", "formula": "count(rows in standardized events where event_family == health) by bucket"},
            {"metric": "source", "formula": "standardized from dm_health_events"},
        ),
    },
    "repro_events_trend": {
        "label": "Reproduction events trend",
        "description": "Count of reproduction events by day/week with reproducible bucket logic.",
        "chart_kind": "bar",
        "drilldown_object_type": "events",
        "default_days": 30,
        "default_grain": "day",
        "formula_rows": (
            {"metric": "value", "formula": "count(rows in standardized events where event_family == reproduction) by bucket"},
            {"metric": "source", "formula": "standardized from dm_repro_events"},
        ),
    },
    "milk_quality_trend": {
        "label": "Milk quality trend",
        "description": "High-SCC share by day/week for action-relevant milk quality watch.",
        "chart_kind": "line",
        "drilldown_object_type": "animals",
        "default_days": 30,
        "default_grain": "day",
        "formula_rows": (
            {"metric": "value", "formula": "100 * count(scc_cells_ml >= scc_threshold) / count(records with non-null scc_cells_ml) by bucket"},
            {"metric": "aux", "formula": "avg_scc_cells_ml also exported for reproducibility"},
        ),
    },
    "dim_milk_curve": {
        "label": "DIM milk curve",
        "description": "DIM-based milk view with site/group compare where applicable, built from bucketed DIM aggregates.",
        "chart_kind": "line",
        "drilldown_object_type": "animals",
        "default_days": 30,
        "default_grain": "day",
        "formula_rows": (
            {"metric": "value", "formula": "avg(milk_kg) grouped by floor(dim / dim_bucket_size)"},
            {"metric": "bucket_label", "formula": "[n*dim_bucket_size, (n+1)*dim_bucket_size-1]"},
        ),
    },
}


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize_report_type(value: str | None) -> str:
    key = str(value or "milk_output_trend").strip().lower()
    return key if key in TREND_REPORT_TYPES else "milk_output_trend"


def _normalize_compare_mode(value: str | None) -> str:
    key = str(value or "none").strip().lower()
    return key if key in TREND_COMPARE_MODES else "none"


def _normalize_grain(value: str | None) -> str:
    key = str(value or "day").strip().lower()
    return key if key in TREND_GRAINS else "day"


def _report_def(report_type: str | None) -> dict[str, Any]:
    return dict(TREND_REPORT_DEFS[_normalize_report_type(report_type)])


def _period_bounds(*, asof_date: date, days: int) -> tuple[date, date]:
    safe_days = max(1, int(days or 1))
    start = asof_date - timedelta(days=safe_days - 1)
    return start, asof_date


def _prev_period_bounds(*, start: date, days: int) -> tuple[date, date]:
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=max(1, int(days or 1)) - 1)
    return prev_start, prev_end


def _animals_context(*, input_dir: Path, asof_date: date) -> pd.DataFrame:
    animals = _read_csv(input_dir / "dm_animals.csv")
    assn = _join_pen_assignments(input_dir=input_dir, asof_date=asof_date)
    if animals.empty:
        cols = ["animal_id", "farm_id", "site_id", "pen_id", "pen_name", "status", "breed", "sex"]
        return pd.DataFrame(columns=cols)
    ctx = animals[[c for c in ("animal_id", "farm_id", "site_id", "status", "breed", "sex") if c in animals.columns]].copy()
    if not assn.empty:
        ctx = ctx.merge(assn[["animal_id", "pen_id", "pen_name"]].drop_duplicates("animal_id"), on="animal_id", how="left")
    else:
        if "current_pen_id" in animals.columns:
            ctx["pen_id"] = animals.get("current_pen_id")
        if "current_pen_name" in animals.columns:
            ctx["pen_name"] = animals.get("current_pen_name")
    for col in ("pen_id", "pen_name"):
        if col not in ctx.columns:
            ctx[col] = pd.NA
    return ctx


def _build_milk_records_df(*, input_dir: Path, asof_date: date) -> pd.DataFrame:
    path = input_dir / "dm_milkings_daily.csv"
    if path.exists():
        df = _read_csv(path)
        if not df.empty:
            out = df.copy()
            if "date" in out.columns:
                out["record_date"] = pd.to_datetime(out.get("date"), errors="coerce")
            else:
                out["record_date"] = pd.NaT
            if "milk_kg" not in out.columns:
                out["milk_kg"] = pd.NA
            if "dim" not in out.columns:
                out["dim"] = pd.NA
            if "scc_cells_ml" not in out.columns:
                out["scc_cells_ml"] = pd.NA
            ctx = _animals_context(input_dir=input_dir, asof_date=asof_date)
            if not ctx.empty:
                for col in ("farm_id", "site_id", "pen_id", "pen_name", "status", "breed", "sex"):
                    if col not in out.columns and col in ctx.columns:
                        out = out.merge(ctx[["animal_id", col]].drop_duplicates("animal_id"), on="animal_id", how="left")
            return out

    path = input_dir / "dm_testday.csv"
    if path.exists():
        df = _read_csv(path)
        if not df.empty:
            out = df.copy()
            out["record_date"] = pd.to_datetime(out.get("test_date"), errors="coerce")
            if "scc_cells_ml" not in out.columns:
                out["scc_cells_ml"] = pd.NA
            ctx = _animals_context(input_dir=input_dir, asof_date=asof_date)
            if not ctx.empty:
                out = out.merge(ctx.drop_duplicates("animal_id"), on="animal_id", how="left")
            return out

    return pd.DataFrame(columns=["animal_id", "record_date", "milk_kg", "dim", "scc_cells_ml", "farm_id", "site_id", "pen_id", "pen_name"])


def _build_event_records_df(*, input_dir: Path, asof_date: date) -> pd.DataFrame:
    df = _build_events_df(input_dir=input_dir, asof_date=asof_date)
    if df.empty:
        return df
    out = df.copy()
    out["event_date_ts"] = pd.to_datetime(out.get("event_date"), errors="coerce")
    return out


def _apply_base_filters(df: pd.DataFrame, *, filters: Mapping[str, Any], ignore_fields: Sequence[str] = ()) -> pd.DataFrame:
    out = df.copy()
    ignored = {str(x) for x in ignore_fields}
    for name, raw in dict(filters or {}).items():
        if name in ignored or raw in (None, "", []):
            continue
        if name not in out.columns:
            continue
        out = out[out[name].astype(str).str.lower() == str(raw).strip().lower()]
    return out


def _filter_period(df: pd.DataFrame, *, date_col: str, start: date, end: date) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    out = df.copy()
    out[date_col] = pd.to_datetime(out.get(date_col), errors="coerce")
    return out[(out[date_col].dt.date >= start) & (out[date_col].dt.date <= end)]


def _bucket_daily(df: pd.DataFrame, *, date_col: str, grain: str, bucket_prefix: str) -> pd.DataFrame:
    out = df.copy()
    out[date_col] = pd.to_datetime(out.get(date_col), errors="coerce")
    if _normalize_grain(grain) == "week":
        week_start = out[date_col] - pd.to_timedelta(out[date_col].dt.weekday.fillna(0).astype(int), unit="D")
        out["bucket_start"] = week_start.dt.normalize()
        out["bucket_end"] = out["bucket_start"] + pd.Timedelta(days=6)
        out["bucket_label"] = out["bucket_start"].dt.strftime("%Y-%m-%d")
    else:
        out["bucket_start"] = out[date_col].dt.normalize()
        out["bucket_end"] = out[date_col].dt.normalize()
        out["bucket_label"] = out[date_col].dt.strftime("%Y-%m-%d")
    out["bucket_id"] = bucket_prefix + out["bucket_start"].dt.strftime("%Y-%m-%d")
    return out


def _bucket_dim(df: pd.DataFrame, *, dim_bucket_size: int) -> pd.DataFrame:
    out = df.copy()
    dim = pd.to_numeric(out.get("dim"), errors="coerce")
    size = max(5, int(dim_bucket_size or 30))
    bucket_start = (dim.fillna(-1) // size) * size
    out = out[bucket_start >= 0].copy()
    bucket_start = bucket_start[bucket_start >= 0].astype(int)
    out["bucket_start_dim"] = bucket_start.values
    out["bucket_end_dim"] = out["bucket_start_dim"] + size - 1
    out["bucket_label"] = out["bucket_start_dim"].astype(str) + "-" + out["bucket_end_dim"].astype(str)
    out["bucket_id"] = "dim:" + out["bucket_label"].astype(str)
    out["bucket_start"] = pd.to_datetime("1970-01-01")
    out["bucket_end"] = pd.to_datetime("1970-01-01")
    return out


def _aggregate_series(df: pd.DataFrame, *, report_type: str) -> pd.DataFrame:
    key = _normalize_report_type(report_type)
    if df.empty:
        return pd.DataFrame(columns=["bucket_id", "bucket_label", "bucket_start", "bucket_end", "value", "records", "animals", "avg_scc_cells_ml"])
    group_cols = ["bucket_id", "bucket_label", "bucket_start", "bucket_end"]
    if key == "milk_output_trend" or key == "dim_milk_curve":
        out = df.groupby(group_cols, dropna=False).agg(
            value=("milk_kg", "mean"),
            records=("animal_id", "size"),
            animals=("animal_id", pd.Series.nunique),
        ).reset_index()
        out["value"] = pd.to_numeric(out.get("value"), errors="coerce").round(2)
        return out
    if key == "milk_quality_trend":
        tmp = df.copy()
        scc = pd.to_numeric(tmp.get("scc_cells_ml"), errors="coerce")
        threshold = pd.to_numeric(tmp.get("scc_threshold"), errors="coerce").fillna(200000)
        tmp["high_scc_flag"] = (scc >= threshold).astype(int)
        tmp["scc_observed"] = scc.notna().astype(int)
        out = tmp.groupby(group_cols, dropna=False).agg(
            high_scc=("high_scc_flag", "sum"),
            scc_observed=("scc_observed", "sum"),
            avg_scc_cells_ml=("scc_cells_ml", "mean"),
            animals=("animal_id", pd.Series.nunique),
        ).reset_index()
        denom = pd.to_numeric(out.get("scc_observed"), errors="coerce").replace({0: pd.NA})
        out["value"] = (pd.to_numeric(out.get("high_scc"), errors="coerce") / denom * 100.0).round(2)
        out["records"] = pd.to_numeric(out.get("scc_observed"), errors="coerce").fillna(0).astype(int)
        out["avg_scc_cells_ml"] = pd.to_numeric(out.get("avg_scc_cells_ml"), errors="coerce").round(0)
        return out[group_cols + ["value", "records", "animals", "avg_scc_cells_ml"]]
    out = df.groupby(group_cols, dropna=False).agg(
        value=("event_id", "size"),
        records=("event_id", "size"),
        animals=("animal_id", pd.Series.nunique),
    ).reset_index()
    out["value"] = pd.to_numeric(out.get("value"), errors="coerce").fillna(0).astype(int)
    return out


def _series_label(compare_mode: str, primary_id: str, fallback: str) -> str:
    mode = _normalize_compare_mode(compare_mode)
    if mode == "site" and primary_id:
        return f"site:{primary_id}"
    if mode == "group" and primary_id:
        return f"group:{primary_id}"
    return fallback


def _select_dimension_ids(df: pd.DataFrame, *, compare_mode: str, primary_id: str, compare_id: str) -> tuple[str, str]:
    mode = _normalize_compare_mode(compare_mode)
    if mode == "site":
        ids = [str(x) for x in df.get("site_id", pd.Series(dtype=object)).dropna().astype(str).unique().tolist() if str(x).strip()]
    elif mode == "group":
        ids = [str(x) for x in df.get("pen_id", pd.Series(dtype=object)).dropna().astype(str).unique().tolist() if str(x).strip()]
    else:
        return primary_id, compare_id
    ids = sorted(dict.fromkeys(ids))
    if not primary_id and ids:
        primary_id = ids[0]
    if not compare_id and len(ids) > 1:
        compare_id = next((x for x in ids if x != primary_id), "")
    return primary_id, compare_id


def _merge_period_compare(*, current_agg: pd.DataFrame, compare_agg: pd.DataFrame, primary_label: str, compare_label: str) -> pd.DataFrame:
    cur = current_agg.sort_values("bucket_start").reset_index(drop=True).copy()
    cmp = compare_agg.sort_values("bucket_start").reset_index(drop=True).copy()
    cur["bucket_index"] = range(len(cur))
    cmp["bucket_index"] = range(len(cmp))
    merged = cur.merge(
        cmp[["bucket_index", "bucket_start", "bucket_end", "value", "records", "animals"]].rename(
            columns={
                "bucket_start": "compare_bucket_start",
                "bucket_end": "compare_bucket_end",
                "value": "compare_value",
                "records": "compare_records",
                "animals": "compare_animals",
            }
        ),
        on="bucket_index",
        how="left",
    )
    merged["current_value"] = pd.to_numeric(merged.get("value"), errors="coerce")
    merged["current_records"] = merged.get("records")
    merged["current_animals"] = merged.get("animals")
    merged["delta_abs"] = (pd.to_numeric(merged.get("current_value"), errors="coerce") - pd.to_numeric(merged.get("compare_value"), errors="coerce")).round(2)
    denom = pd.to_numeric(merged.get("compare_value"), errors="coerce").replace({0: pd.NA})
    merged["delta_pct"] = (merged["delta_abs"] / denom * 100.0).round(2)
    merged["primary_label"] = primary_label
    merged["compare_label"] = compare_label
    return merged


def _merge_dimension_compare(*, current_agg: pd.DataFrame, compare_agg: pd.DataFrame, primary_label: str, compare_label: str) -> pd.DataFrame:
    merged = current_agg.merge(
        compare_agg[["bucket_id", "value", "records", "animals"]].rename(columns={"value": "compare_value", "records": "compare_records", "animals": "compare_animals"}),
        on="bucket_id",
        how="left",
    )
    merged["current_value"] = pd.to_numeric(merged.get("value"), errors="coerce")
    merged["current_records"] = merged.get("records")
    merged["current_animals"] = merged.get("animals")
    merged["delta_abs"] = (pd.to_numeric(merged.get("current_value"), errors="coerce") - pd.to_numeric(merged.get("compare_value"), errors="coerce")).round(2)
    denom = pd.to_numeric(merged.get("compare_value"), errors="coerce").replace({0: pd.NA})
    merged["delta_pct"] = (merged["delta_abs"] / denom * 100.0).round(2)
    merged["primary_label"] = primary_label
    merged["compare_label"] = compare_label
    return merged


def _no_compare_rows(*, agg: pd.DataFrame, primary_label: str) -> pd.DataFrame:
    out = agg.copy()
    out["current_value"] = pd.to_numeric(out.get("value"), errors="coerce")
    out["compare_value"] = pd.NA
    out["delta_abs"] = pd.NA
    out["delta_pct"] = pd.NA
    out["current_records"] = out.get("records")
    out["compare_records"] = pd.NA
    out["current_animals"] = out.get("animals")
    out["compare_animals"] = pd.NA
    out["primary_label"] = primary_label
    out["compare_label"] = ""
    out["compare_bucket_start"] = pd.NaT
    out["compare_bucket_end"] = pd.NaT
    return out


def _summary_rows(*, merged: pd.DataFrame, compare_mode: str, primary_label: str, compare_label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cur = pd.to_numeric(merged.get("current_value"), errors="coerce")
    rows.append({"metric": f"current_total[{primary_label}]", "value": round(float(cur.dropna().sum()), 2) if not cur.dropna().empty else 0.0})
    rows.append({"metric": f"current_peak[{primary_label}]", "value": round(float(cur.dropna().max()), 2) if not cur.dropna().empty else 0.0})
    if _normalize_compare_mode(compare_mode) != "none" and compare_label:
        cmp = pd.to_numeric(merged.get("compare_value"), errors="coerce")
        rows.append({"metric": f"compare_total[{compare_label}]", "value": round(float(cmp.dropna().sum()), 2) if not cmp.dropna().empty else 0.0})
        delta = round(float(cur.dropna().sum()) - float(cmp.dropna().sum()), 2) if not cur.dropna().empty and not cmp.dropna().empty else pd.NA
        rows.append({"metric": "delta_total", "value": delta})
    return rows


def _build_chart_rows(
    *,
    input_dir: Path,
    asof_date: date,
    report_type: str,
    role: str,
    filters: Mapping[str, Any] | None = None,
    period_days: int = 30,
    grain: str = "day",
    compare_mode: str = "none",
    compare_site_id: str | None = None,
    compare_pen_id: str | None = None,
    dim_bucket_size: int = 30,
    scc_threshold: int = 200_000,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    key = _normalize_report_type(report_type)
    comp = _normalize_compare_mode(compare_mode)
    role_norm = _role_key(role)
    flt = {str(k): v for k, v in dict(filters or {}).items()}
    cur_start, cur_end = _period_bounds(asof_date=asof_date, days=int(period_days))
    prev_start, prev_end = _prev_period_bounds(start=cur_start, days=int(period_days))

    if key in {"milk_output_trend", "milk_quality_trend", "dim_milk_curve"}:
        base = _build_milk_records_df(input_dir=input_dir, asof_date=asof_date)
        base = _apply_base_filters(base, filters=flt)
        base["scc_threshold"] = int(scc_threshold)
        if key == "dim_milk_curve":
            current = _filter_period(base, date_col="record_date", start=cur_start, end=cur_end)
            current = _bucket_dim(current, dim_bucket_size=int(dim_bucket_size))
            primary_pen, compare_pen = "", str(compare_pen_id or "").strip()
            primary_site, compare_site = "", str(compare_site_id or "").strip()
            if comp == "site":
                primary_site, compare_site = _select_dimension_ids(current, compare_mode=comp, primary_id=str(flt.get("site_id") or "").strip(), compare_id=compare_site)
                current_agg = _aggregate_series(current[current.get("site_id", pd.Series(dtype=object)).astype(str) == primary_site], report_type=key)
                compare_agg = _aggregate_series(current[current.get("site_id", pd.Series(dtype=object)).astype(str) == compare_site], report_type=key) if compare_site else pd.DataFrame(columns=current_agg.columns)
                merged = _merge_dimension_compare(current_agg=current_agg, compare_agg=compare_agg, primary_label=_series_label(comp, primary_site, "current"), compare_label=_series_label(comp, compare_site, "compare")) if compare_site else _no_compare_rows(agg=current_agg, primary_label=_series_label(comp, primary_site, "current"))
            elif comp == "group":
                primary_pen, compare_pen = _select_dimension_ids(current, compare_mode=comp, primary_id=str(flt.get("pen_id") or "").strip(), compare_id=compare_pen)
                current_agg = _aggregate_series(current[current.get("pen_id", pd.Series(dtype=object)).astype(str) == primary_pen], report_type=key)
                compare_agg = _aggregate_series(current[current.get("pen_id", pd.Series(dtype=object)).astype(str) == compare_pen], report_type=key) if compare_pen else pd.DataFrame(columns=current_agg.columns)
                merged = _merge_dimension_compare(current_agg=current_agg, compare_agg=compare_agg, primary_label=_series_label(comp, primary_pen, "current"), compare_label=_series_label(comp, compare_pen, "compare")) if compare_pen else _no_compare_rows(agg=current_agg, primary_label=_series_label(comp, primary_pen, "current"))
            else:
                current_agg = _aggregate_series(current, report_type=key)
                merged = _no_compare_rows(agg=current_agg, primary_label="current")
            context = {
                "dataset": "milk",
                "role": role_norm,
                "current_start": cur_start.isoformat(),
                "current_end": cur_end.isoformat(),
                "compare_start": "",
                "compare_end": "",
                "compare_mode": comp,
                "primary_label": str(merged.get("primary_label", pd.Series(dtype=object)).iloc[0]) if not merged.empty else "current",
                "compare_label": str(merged.get("compare_label", pd.Series(dtype=object)).iloc[0]) if not merged.empty else "",
            }
            return merged.sort_values("bucket_label").reset_index(drop=True), context

        current = _filter_period(base, date_col="record_date", start=cur_start, end=cur_end)
        current = _bucket_daily(current, date_col="record_date", grain=grain, bucket_prefix="date:")
        if comp == "period":
            compare = _filter_period(base, date_col="record_date", start=prev_start, end=prev_end)
            compare = _bucket_daily(compare, date_col="record_date", grain=grain, bucket_prefix="date:")
            current_agg = _aggregate_series(current, report_type=key)
            compare_agg = _aggregate_series(compare, report_type=key)
            merged = _merge_period_compare(current_agg=current_agg, compare_agg=compare_agg, primary_label="current", compare_label="previous_period")
        elif comp == "site":
            primary_site, compare_site = _select_dimension_ids(current, compare_mode=comp, primary_id=str(flt.get("site_id") or "").strip(), compare_id=str(compare_site_id or "").strip())
            current_agg = _aggregate_series(current[current.get("site_id", pd.Series(dtype=object)).astype(str) == primary_site], report_type=key)
            compare_agg = _aggregate_series(current[current.get("site_id", pd.Series(dtype=object)).astype(str) == compare_site], report_type=key) if compare_site else pd.DataFrame(columns=current_agg.columns)
            merged = _merge_dimension_compare(current_agg=current_agg, compare_agg=compare_agg, primary_label=_series_label(comp, primary_site, "current"), compare_label=_series_label(comp, compare_site, "compare")) if compare_site else _no_compare_rows(agg=current_agg, primary_label=_series_label(comp, primary_site, "current"))
        elif comp == "group":
            primary_pen, compare_pen = _select_dimension_ids(current, compare_mode=comp, primary_id=str(flt.get("pen_id") or "").strip(), compare_id=str(compare_pen_id or "").strip())
            current_agg = _aggregate_series(current[current.get("pen_id", pd.Series(dtype=object)).astype(str) == primary_pen], report_type=key)
            compare_agg = _aggregate_series(current[current.get("pen_id", pd.Series(dtype=object)).astype(str) == compare_pen], report_type=key) if compare_pen else pd.DataFrame(columns=current_agg.columns)
            merged = _merge_dimension_compare(current_agg=current_agg, compare_agg=compare_agg, primary_label=_series_label(comp, primary_pen, "current"), compare_label=_series_label(comp, compare_pen, "compare")) if compare_pen else _no_compare_rows(agg=current_agg, primary_label=_series_label(comp, primary_pen, "current"))
        else:
            current_agg = _aggregate_series(current, report_type=key)
            merged = _no_compare_rows(agg=current_agg, primary_label="current")
        context = {
            "dataset": "milk",
            "role": role_norm,
            "current_start": cur_start.isoformat(),
            "current_end": cur_end.isoformat(),
            "compare_start": prev_start.isoformat() if comp == "period" else "",
            "compare_end": prev_end.isoformat() if comp == "period" else "",
            "compare_mode": comp,
            "primary_label": str(merged.get("primary_label", pd.Series(dtype=object)).iloc[0]) if not merged.empty else "current",
            "compare_label": str(merged.get("compare_label", pd.Series(dtype=object)).iloc[0]) if not merged.empty else "",
        }
        return merged.sort_values("bucket_start").reset_index(drop=True), context

    base = _build_event_records_df(input_dir=input_dir, asof_date=asof_date)
    if key == "health_events_trend":
        base = base[base.get("event_family", pd.Series(dtype=object)).astype(str).str.lower() == "health"]
    elif key == "repro_events_trend":
        base = base[base.get("event_family", pd.Series(dtype=object)).astype(str).str.lower() == "reproduction"]
    base = _apply_base_filters(base, filters=flt)
    current = _filter_period(base, date_col="event_date_ts", start=cur_start, end=cur_end)
    current = _bucket_daily(current, date_col="event_date_ts", grain=grain, bucket_prefix="date:")
    if comp == "period":
        compare = _filter_period(base, date_col="event_date_ts", start=prev_start, end=prev_end)
        compare = _bucket_daily(compare, date_col="event_date_ts", grain=grain, bucket_prefix="date:")
        current_agg = _aggregate_series(current, report_type=key)
        compare_agg = _aggregate_series(compare, report_type=key)
        merged = _merge_period_compare(current_agg=current_agg, compare_agg=compare_agg, primary_label="current", compare_label="previous_period")
    elif comp == "site":
        primary_site, compare_site = _select_dimension_ids(current, compare_mode=comp, primary_id=str(flt.get("site_id") or "").strip(), compare_id=str(compare_site_id or "").strip())
        current_agg = _aggregate_series(current[current.get("site_id", pd.Series(dtype=object)).astype(str) == primary_site], report_type=key)
        compare_agg = _aggregate_series(current[current.get("site_id", pd.Series(dtype=object)).astype(str) == compare_site], report_type=key) if compare_site else pd.DataFrame(columns=current_agg.columns)
        merged = _merge_dimension_compare(current_agg=current_agg, compare_agg=compare_agg, primary_label=_series_label(comp, primary_site, "current"), compare_label=_series_label(comp, compare_site, "compare")) if compare_site else _no_compare_rows(agg=current_agg, primary_label=_series_label(comp, primary_site, "current"))
    elif comp == "group":
        primary_pen, compare_pen = _select_dimension_ids(current, compare_mode=comp, primary_id=str(flt.get("pen_id") or "").strip(), compare_id=str(compare_pen_id or "").strip())
        current_agg = _aggregate_series(current[current.get("pen_id", pd.Series(dtype=object)).astype(str) == primary_pen], report_type=key)
        compare_agg = _aggregate_series(current[current.get("pen_id", pd.Series(dtype=object)).astype(str) == compare_pen], report_type=key) if compare_pen else pd.DataFrame(columns=current_agg.columns)
        merged = _merge_dimension_compare(current_agg=current_agg, compare_agg=compare_agg, primary_label=_series_label(comp, primary_pen, "current"), compare_label=_series_label(comp, compare_pen, "compare")) if compare_pen else _no_compare_rows(agg=current_agg, primary_label=_series_label(comp, primary_pen, "current"))
    else:
        current_agg = _aggregate_series(current, report_type=key)
        merged = _no_compare_rows(agg=current_agg, primary_label="current")
    context = {
        "dataset": "events",
        "role": role_norm,
        "current_start": cur_start.isoformat(),
        "current_end": cur_end.isoformat(),
        "compare_start": prev_start.isoformat() if comp == "period" else "",
        "compare_end": prev_end.isoformat() if comp == "period" else "",
        "compare_mode": comp,
        "primary_label": str(merged.get("primary_label", pd.Series(dtype=object)).iloc[0]) if not merged.empty else "current",
        "compare_label": str(merged.get("compare_label", pd.Series(dtype=object)).iloc[0]) if not merged.empty else "",
    }
    return merged.sort_values("bucket_start").reset_index(drop=True), context


def build_trend_report_snapshot(
    *,
    input_dir: Path,
    asof_date: date,
    role: str,
    report_type: str,
    filters: Mapping[str, Any] | None = None,
    period_days: int = 30,
    grain: str = "day",
    compare_mode: str = "none",
    compare_site_id: str | None = None,
    compare_pen_id: str | None = None,
    dim_bucket_size: int = 30,
    scc_threshold: int = 200_000,
) -> dict[str, Any]:
    rep = _report_def(report_type)
    key = _normalize_report_type(report_type)
    rows_df, context = _build_chart_rows(
        input_dir=Path(input_dir),
        asof_date=asof_date,
        report_type=key,
        role=role,
        filters=filters,
        period_days=int(period_days),
        grain=_normalize_grain(grain),
        compare_mode=_normalize_compare_mode(compare_mode),
        compare_site_id=compare_site_id,
        compare_pen_id=compare_pen_id,
        dim_bucket_size=int(dim_bucket_size),
        scc_threshold=int(scc_threshold),
    )
    summary_rows = _summary_rows(
        merged=rows_df,
        compare_mode=str(context.get("compare_mode") or "none"),
        primary_label=str(context.get("primary_label") or "current"),
        compare_label=str(context.get("compare_label") or ""),
    )
    chart_rows = rows_df.copy()
    for col in ("bucket_start", "bucket_end", "compare_bucket_start", "compare_bucket_end"):
        if col in chart_rows.columns:
            chart_rows[col] = pd.to_datetime(chart_rows[col], errors="coerce").dt.strftime("%Y-%m-%d")
    return {
        "report_type": key,
        "label": str(rep.get("label") or key),
        "description": str(rep.get("description") or ""),
        "chart_kind": str(rep.get("chart_kind") or "line"),
        "drilldown_object_type": str(rep.get("drilldown_object_type") or "animals"),
        "role": _role_key(role),
        "filters": dict(filters or {}),
        "period_days": int(period_days),
        "grain": _normalize_grain(grain),
        "compare_mode": str(context.get("compare_mode") or "none"),
        "compare_site_id": str(compare_site_id or ""),
        "compare_pen_id": str(compare_pen_id or ""),
        "dim_bucket_size": int(dim_bucket_size),
        "scc_threshold": int(scc_threshold),
        "primary_label": str(context.get("primary_label") or "current"),
        "compare_label": str(context.get("compare_label") or ""),
        "current_period": {"start": str(context.get("current_start") or ""), "end": str(context.get("current_end") or "")},
        "compare_period": {"start": str(context.get("compare_start") or ""), "end": str(context.get("compare_end") or "")},
        "chart_rows": chart_rows.to_dict(orient="records"),
        "summary_rows": summary_rows,
        "formula_rows": [dict(x) for x in list(rep.get("formula_rows") or [])],
    }


def build_trend_chart_table(snapshot: Mapping[str, Any]) -> pd.DataFrame:
    rows = list(snapshot.get("chart_rows") or [])
    return pd.DataFrame(rows)


def build_trend_chart_frame(snapshot: Mapping[str, Any]) -> pd.DataFrame:
    df = build_trend_chart_table(snapshot)
    if df.empty:
        return pd.DataFrame(columns=[str(snapshot.get("primary_label") or "current")])
    primary = str(snapshot.get("primary_label") or "current")
    compare = str(snapshot.get("compare_label") or "").strip()
    out = pd.DataFrame({
        primary: pd.to_numeric(df.get("current_value"), errors="coerce"),
    }, index=df.get("bucket_label"))
    if compare:
        out[compare] = pd.to_numeric(df.get("compare_value"), errors="coerce")
    out.index.name = "bucket_label"
    return out


def build_trend_bucket_options(snapshot: Mapping[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in list(snapshot.get("chart_rows") or []):
        out.append({
            "bucket_id": str(row.get("bucket_id") or ""),
            "label": f"{row.get('bucket_label') or '—'} · current={row.get('current_value') or 0}",
        })
    return out


def build_trend_drilldown(
    *,
    input_dir: Path,
    asof_date: date,
    snapshot: Mapping[str, Any],
    bucket_id: str,
    limit: int = 200,
) -> dict[str, Any]:
    report_type = _normalize_report_type(snapshot.get("report_type"))
    filters = dict(snapshot.get("filters") or {})
    compare_mode = _normalize_compare_mode(snapshot.get("compare_mode"))
    period_days = int(snapshot.get("period_days") or 30)
    grain = _normalize_grain(snapshot.get("grain"))
    dim_bucket_size = int(snapshot.get("dim_bucket_size") or 30)
    scc_threshold = int(snapshot.get("scc_threshold") or 200000)
    chart_rows = pd.DataFrame(list(snapshot.get("chart_rows") or []))
    chosen = chart_rows[chart_rows.get("bucket_id", pd.Series(dtype=object)).astype(str) == str(bucket_id)]
    if chosen.empty:
        return {"object_type": str(snapshot.get("drilldown_object_type") or "animals"), "rows": [], "selected_bucket_id": str(bucket_id or "")}
    row = chosen.iloc[0].to_dict()
    rows: pd.DataFrame
    if report_type in {"milk_output_trend", "milk_quality_trend", "dim_milk_curve"}:
        base = _build_milk_records_df(input_dir=Path(input_dir), asof_date=asof_date)
        base = _apply_base_filters(base, filters=filters)
        if report_type == "dim_milk_curve":
            current_start, current_end = _period_bounds(asof_date=asof_date, days=period_days)
            base = _filter_period(base, date_col="record_date", start=current_start, end=current_end)
            base = _bucket_dim(base, dim_bucket_size=dim_bucket_size)
        else:
            current_start, current_end = _period_bounds(asof_date=asof_date, days=period_days)
            base = _filter_period(base, date_col="record_date", start=current_start, end=current_end)
            base = _bucket_daily(base, date_col="record_date", grain=grain, bucket_prefix="date:")
        rows = base[base.get("bucket_id", pd.Series(dtype=object)).astype(str) == str(bucket_id)].copy()
        primary_label = str(snapshot.get("primary_label") or "current")
        compare_label = str(snapshot.get("compare_label") or "").strip()
        if compare_mode == "site":
            primary_site = primary_label.split(":", 1)[-1] if ":" in primary_label else str(filters.get("site_id") or "")
            compare_site = compare_label.split(":", 1)[-1] if ":" in compare_label else str(snapshot.get("compare_site_id") or "")
            rows["series_label"] = rows.get("site_id", pd.Series(dtype=object)).astype(str).map(lambda x: f"site:{x}")
            rows = rows[rows["series_label"].isin([f"site:{primary_site}", f"site:{compare_site}"])]
        elif compare_mode == "group":
            primary_pen = primary_label.split(":", 1)[-1] if ":" in primary_label else str(filters.get("pen_id") or "")
            compare_pen = compare_label.split(":", 1)[-1] if ":" in compare_label else str(snapshot.get("compare_pen_id") or "")
            rows["series_label"] = rows.get("pen_id", pd.Series(dtype=object)).astype(str).map(lambda x: f"group:{x}")
            rows = rows[rows["series_label"].isin([f"group:{primary_pen}", f"group:{compare_pen}"])]
        elif compare_mode == "period" and str(row.get("compare_bucket_start") or ""):
            prev = _build_milk_records_df(input_dir=Path(input_dir), asof_date=asof_date)
            prev = _apply_base_filters(prev, filters=filters)
            if report_type == "dim_milk_curve":
                pass
            else:
                prev = _bucket_daily(prev, date_col="record_date", grain=grain, bucket_prefix="date:")
                prev = _filter_period(prev, date_col="record_date", start=date.fromisoformat(str(row.get("compare_bucket_start"))), end=date.fromisoformat(str(row.get("compare_bucket_end"))))
                prev["series_label"] = "previous_period"
                rows["series_label"] = "current"
                rows = pd.concat([rows, prev], ignore_index=True, sort=False)
        else:
            rows["series_label"] = primary_label
        if report_type == "milk_quality_trend":
            rows = rows.sort_values(["scc_cells_ml", "animal_id"], ascending=[False, True], na_position="last")
        else:
            rows = rows.sort_values(["milk_kg", "animal_id"], ascending=[True, True], na_position="last")
        selected_cols = [c for c in ["series_label", "record_date", "animal_id", "milk_kg", "scc_cells_ml", "dim", "site_id", "pen_id", "pen_name"] if c in rows.columns]
        rows = rows.head(max(1, int(limit)))[selected_cols]
        object_type = "animals"
    else:
        base = _build_event_records_df(input_dir=Path(input_dir), asof_date=asof_date)
        if report_type == "health_events_trend":
            base = base[base.get("event_family", pd.Series(dtype=object)).astype(str).str.lower() == "health"]
        elif report_type == "repro_events_trend":
            base = base[base.get("event_family", pd.Series(dtype=object)).astype(str).str.lower() == "reproduction"]
        base = _apply_base_filters(base, filters=filters)
        base = _bucket_daily(base, date_col="event_date_ts", grain=grain, bucket_prefix="date:")
        rows = base[base.get("bucket_id", pd.Series(dtype=object)).astype(str) == str(bucket_id)].copy()
        primary_label = str(snapshot.get("primary_label") or "current")
        compare_label = str(snapshot.get("compare_label") or "").strip()
        if compare_mode == "site":
            primary_site = primary_label.split(":", 1)[-1] if ":" in primary_label else str(filters.get("site_id") or "")
            compare_site = compare_label.split(":", 1)[-1] if ":" in compare_label else str(snapshot.get("compare_site_id") or "")
            rows["series_label"] = rows.get("site_id", pd.Series(dtype=object)).astype(str).map(lambda x: f"site:{x}")
            rows = rows[rows["series_label"].isin([f"site:{primary_site}", f"site:{compare_site}"])]
        elif compare_mode == "group":
            primary_pen = primary_label.split(":", 1)[-1] if ":" in primary_label else str(filters.get("pen_id") or "")
            compare_pen = compare_label.split(":", 1)[-1] if ":" in compare_label else str(snapshot.get("compare_pen_id") or "")
            rows["series_label"] = rows.get("pen_id", pd.Series(dtype=object)).astype(str).map(lambda x: f"group:{x}")
            rows = rows[rows["series_label"].isin([f"group:{primary_pen}", f"group:{compare_pen}"])]
        elif compare_mode == "period" and str(row.get("compare_bucket_start") or ""):
            prev = _build_event_records_df(input_dir=Path(input_dir), asof_date=asof_date)
            if report_type == "health_events_trend":
                prev = prev[prev.get("event_family", pd.Series(dtype=object)).astype(str).str.lower() == "health"]
            elif report_type == "repro_events_trend":
                prev = prev[prev.get("event_family", pd.Series(dtype=object)).astype(str).str.lower() == "reproduction"]
            prev = _apply_base_filters(prev, filters=filters)
            prev = _bucket_daily(prev, date_col="event_date_ts", grain=grain, bucket_prefix="date:")
            prev = _filter_period(prev, date_col="event_date_ts", start=date.fromisoformat(str(row.get("compare_bucket_start"))), end=date.fromisoformat(str(row.get("compare_bucket_end"))))
            prev["series_label"] = "previous_period"
            rows["series_label"] = "current"
            rows = pd.concat([rows, prev], ignore_index=True, sort=False)
        else:
            rows["series_label"] = primary_label
        rows = rows.sort_values(["event_date_ts", "severity", "animal_id"], ascending=[False, True, True], na_position="last")
        selected_cols = [c for c in ["series_label", "event_date", "event_family", "event_type", "animal_id", "site_id", "pen_id", "pen_name", "severity", "status"] if c in rows.columns]
        rows = rows.head(max(1, int(limit)))[selected_cols]
        object_type = "events"

    return {
        "object_type": object_type,
        "selected_bucket_id": str(bucket_id or ""),
        "bucket_label": str(row.get("bucket_label") or ""),
        "rows": rows.to_dict(orient="records") if not rows.empty else [],
        "returned_rows": int(len(rows)),
    }


def build_trend_drilldown_table(snapshot: Mapping[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(list(snapshot.get("rows") or []))


def export_trend_report(snapshot: Mapping[str, Any], *, fmt: str) -> bytes:
    chart_df = build_trend_chart_table(snapshot)
    summary_df = pd.DataFrame(list(snapshot.get("summary_rows") or []))
    formulas_df = pd.DataFrame(list(snapshot.get("formula_rows") or []))
    kind = str(fmt or "csv").strip().lower()
    if kind == "xlsx":
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            chart_df.to_excel(writer, sheet_name="trend", index=False)
            summary_df.to_excel(writer, sheet_name="summary", index=False)
            formulas_df.to_excel(writer, sheet_name="formulas", index=False)
        return buf.getvalue()
    return chart_df.to_csv(index=False).encode("utf-8")


def export_trend_drilldown(snapshot: Mapping[str, Any], *, fmt: str) -> bytes:
    df = build_trend_drilldown_table(snapshot)
    kind = str(fmt or "csv").strip().lower()
    if kind == "xlsx":
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="drilldown", index=False)
        return buf.getvalue()
    return df.to_csv(index=False).encode("utf-8")


__all__ = [
    "TREND_COMPARE_MODES",
    "TREND_GRAINS",
    "TREND_REPORT_DEFS",
    "TREND_REPORT_TYPES",
    "build_trend_bucket_options",
    "build_trend_chart_frame",
    "build_trend_chart_table",
    "build_trend_drilldown",
    "build_trend_drilldown_table",
    "build_trend_report_snapshot",
    "export_trend_drilldown",
    "export_trend_report",
]

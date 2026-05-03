from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from core.list_builder import (
    _build_animals_df,
    _build_events_df,
    _build_groups_df,
    _normalize_object_type,
    _role_key,
    _apply_sort,
    allowed_columns_for_role,
)
from core.economics import build_cow_value_population_table

REPORT_TYPES: tuple[str, ...] = (
    "animals_overview",
    "groups_overview",
    "events_recent",
    "repro_attention",
    "health_attention",
    "milk_quality_watchlist",
    "cow_value_culling",
)

DEFAULT_SCC_THRESHOLD = 200_000


REPORT_DEFS: dict[str, dict[str, Any]] = {
    "animals_overview": {
        "label": "Animals overview",
        "description": "Быстрый operational report по животным: статус, группа, parity и recent activity.",
        "object_type": "animals",
        "sort_by": "latest_event_date",
        "sort_dir": "desc",
        "selected_columns": ("animal_id", "status", "breed", "parity", "pen_name", "latest_event_date", "active_treatments"),
        "formula_rows": (
            {"metric": "recent_health_events", "formula": "count(dm_health_events by animal_id)"},
            {"metric": "recent_repro_events", "formula": "count(dm_repro_events by animal_id)"},
            {"metric": "active_treatments", "formula": "count(dm_treatments where end_date is null or end_date >= asof_date)"},
        ),
    },
    "groups_overview": {
        "label": "Groups overview",
        "description": "Operational report по группам/pen: численность, загрузка и health concentration.",
        "object_type": "groups",
        "sort_by": "utilization_pct",
        "sort_dir": "desc",
        "selected_columns": ("pen_name", "pen_type", "headcount", "capacity_head", "utilization_pct", "animals_with_health_events_30d"),
        "formula_rows": (
            {"metric": "headcount", "formula": "count(unique animal_id currently assigned to pen)"},
            {"metric": "utilization_pct", "formula": "headcount / capacity_head * 100"},
            {"metric": "animals_with_health_events_30d", "formula": "count(unique animal_id in pen with health event_date >= asof_date-30d)"},
        ),
    },
    "events_recent": {
        "label": "Recent events",
        "description": "Единый recent events report по health / reproduction / treatments.",
        "object_type": "events",
        "sort_by": "event_date_ts",
        "sort_dir": "desc",
        "selected_columns": ("event_date", "event_family", "event_type", "animal_id", "pen_name", "status", "severity"),
        "formula_rows": (
            {"metric": "rows", "formula": "union(dm_health_events, dm_repro_events, dm_treatments) after standardization"},
        ),
    },
    "repro_attention": {
        "label": "Reproduction attention",
        "description": "Быстрый report по reproduction событиям для daily users.",
        "object_type": "events",
        "sort_by": "event_date_ts",
        "sort_dir": "desc",
        "selected_columns": ("event_date", "animal_id", "event_type", "result", "pen_name", "status"),
        "formula_rows": (
            {"metric": "scope", "formula": "event_family == reproduction"},
        ),
    },
    "health_attention": {
        "label": "Health attention",
        "description": "Единый watchlist по health + treatment событиям с linked actions.",
        "object_type": "events",
        "sort_by": "event_date_ts",
        "sort_dir": "desc",
        "selected_columns": ("event_date", "event_family", "animal_id", "event_type", "severity", "status", "withdrawal_until", "pen_name"),
        "formula_rows": (
            {"metric": "scope", "formula": "event_family in [health, treatment]"},
            {"metric": "treatment status", "formula": "planned if start_date > asof_date; completed if end_date < asof_date; else active"},
        ),
    },
    "milk_quality_watchlist": {
        "label": "Milk quality watchlist",
        "description": "Readable watchlist по SCC / active treatments, без full BI DSL.",
        "object_type": "animals",
        "sort_by": "latest_scc_cells_ml",
        "sort_dir": "desc",
        "selected_columns": ("animal_id", "pen_name", "status", "parity", "latest_scc_cells_ml", "milk_quality_flag", "active_treatments", "latest_event_date"),
        "formula_rows": (
            {"metric": "latest_scc_cells_ml", "formula": "latest dm_testday.scc_cells_ml by animal_id else latest dm_lactations.scc_cells_ml"},
            {"metric": "milk_quality_flag", "formula": f"high_scc if latest_scc_cells_ml >= {DEFAULT_SCC_THRESHOLD}; treatment_withdrawal if active_treatments > 0; else ok"},
        ),
    },

    "cow_value_culling": {
        "label": "Cow value / culling",
        "description": "Operational economics report по коровам: keep / breed / treat / cull / defer с replacement comparison.",
        "object_type": "animals",
        "sort_by": "delta_keep_vs_replace_rub",
        "sort_dir": "asc",
        "selected_columns": ("animal_id", "pen_name", "status", "parity", "avg_milk_7d", "latest_scc_cells_ml", "repro_state", "keep_value_rub", "replacement_value_rub", "delta_keep_vs_replace_rub", "recommended_action", "expected_impact_rub"),
        "formula_rows": (
            {"metric": "keep_value_rub", "formula": "(avg_milk_7d * milk_price - daily_feed - daily_other) * horizon - health_penalty - repro_penalty - parity_penalty"},
            {"metric": "replacement_value_rub", "formula": "replacement_expected_daily_margin * horizon - replacement_purchase_cost + cull_salvage - cull_transaction_cost"},
            {"metric": "delta_keep_vs_replace_rub", "formula": "keep_value_rub - replacement_value_rub"},
            {"metric": "recommended_action", "formula": "best enabled scenario; cull requires explicit user confirmation and minimum advantage"},
        ),
    },
}


@dataclass(frozen=True)
class OperationalReportSnapshot:
    report_type: str
    label: str
    description: str
    object_type: str
    role: str
    rows: list[dict[str, Any]]
    total_before_limit: int
    returned_rows: int
    available_columns: tuple[str, ...]
    visible_columns: tuple[str, ...]
    selected_columns: tuple[str, ...]
    sort_by: str
    sort_dir: str
    filters: dict[str, Any]
    summary_rows: list[dict[str, Any]]
    formula_rows: list[dict[str, str]]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _report_def(report_type: str) -> dict[str, Any]:
    key = str(report_type or "animals_overview").strip().lower()
    return dict(REPORT_DEFS.get(key) or REPORT_DEFS["animals_overview"])


def _latest_scc_by_animal(*, input_dir: Path) -> pd.DataFrame:
    testday = pd.DataFrame()
    path = Path(input_dir) / "dm_testday.csv"
    if path.exists():
        try:
            testday = pd.read_csv(path)
        except Exception:
            testday = pd.DataFrame()
    if not testday.empty and "animal_id" in testday.columns and "scc_cells_ml" in testday.columns:
        testday = testday.copy()
        testday["record_ts"] = pd.to_datetime(testday.get("test_date"), errors="coerce")
        latest = testday.sort_values(["animal_id", "record_ts"], ascending=[True, False]).groupby("animal_id", as_index=False).head(1)
        return latest[["animal_id", "scc_cells_ml"]].rename(columns={"scc_cells_ml": "latest_scc_cells_ml"})

    lact = pd.DataFrame()
    path = Path(input_dir) / "dm_lactations.csv"
    if path.exists():
        try:
            lact = pd.read_csv(path)
        except Exception:
            lact = pd.DataFrame()
    if not lact.empty and "animal_id" in lact.columns and "scc_cells_ml" in lact.columns:
        lact = lact.copy()
        lact["record_ts"] = pd.to_datetime(lact.get("calving_date"), errors="coerce")
        latest = lact.sort_values(["animal_id", "record_ts"], ascending=[True, False]).groupby("animal_id", as_index=False).head(1)
        return latest[["animal_id", "scc_cells_ml"]].rename(columns={"scc_cells_ml": "latest_scc_cells_ml"})
    return pd.DataFrame(columns=["animal_id", "latest_scc_cells_ml"])


def _augment_animals_for_reports(df: pd.DataFrame, *, input_dir: Path, scc_threshold: int) -> pd.DataFrame:
    out = df.copy()
    latest_scc = _latest_scc_by_animal(input_dir=input_dir)
    if not latest_scc.empty:
        out = out.merge(latest_scc, on="animal_id", how="left")
    if "latest_scc_cells_ml" not in out.columns:
        out["latest_scc_cells_ml"] = pd.NA
    scc = pd.to_numeric(out.get("latest_scc_cells_ml"), errors="coerce")
    active_treatments = pd.to_numeric(out.get("active_treatments"), errors="coerce").fillna(0)
    out["milk_quality_flag"] = "ok"
    out.loc[active_treatments > 0, "milk_quality_flag"] = "treatment_withdrawal"
    out.loc[scc >= int(scc_threshold), "milk_quality_flag"] = "high_scc"
    return out


def _base_df(*, input_dir: Path, asof_date: date, object_type: str, scc_threshold: int, report_type: str) -> pd.DataFrame:
    otype = _normalize_object_type(object_type)
    if str(report_type or '').strip().lower() == 'cow_value_culling':
        return build_cow_value_population_table(input_dir=input_dir, asof_date=asof_date, limit=500)
    if otype == "animals":
        return _augment_animals_for_reports(_build_animals_df(input_dir=input_dir, asof_date=asof_date), input_dir=input_dir, scc_threshold=scc_threshold)
    if otype == "groups":
        return _build_groups_df(input_dir=input_dir, asof_date=asof_date)
    return _build_events_df(input_dir=input_dir, asof_date=asof_date)


def _apply_report_filters(df: pd.DataFrame, *, report_type: str, filters: Mapping[str, Any], scc_threshold: int) -> pd.DataFrame:
    out = df.copy()
    key = str(report_type or "").strip().lower()
    if key == "repro_attention":
        out = out[out.get("event_family", pd.Series(dtype=object)).astype(str).str.lower() == "reproduction"]
    elif key == "health_attention":
        family = out.get("event_family", pd.Series(dtype=object)).astype(str).str.lower()
        out = out[family.isin(["health", "treatment"])]
    elif key == "milk_quality_watchlist":
        scc = pd.to_numeric(out.get("latest_scc_cells_ml"), errors="coerce")
        treatments = pd.to_numeric(out.get("active_treatments"), errors="coerce").fillna(0)
        out = out[(scc >= int(scc_threshold)) | (treatments > 0)]

    for name, raw in dict(filters or {}).items():
        if raw in (None, "", []):
            continue
        if name == "q":
            q = str(raw).strip().lower()
            cols = [c for c in ("animal_id", "pen_name", "event_type", "event_family", "status", "milk_quality_flag") if c in out.columns]
            mask = pd.Series([False] * len(out), index=out.index)
            for col in cols:
                mask = mask | out[col].astype(str).str.lower().str.contains(q, na=False)
            out = out[mask]
        elif name in out.columns:
            out = out[out[name].astype(str).str.lower() == str(raw).strip().lower()]
    return out


def _selected_columns(*, report_type: str, role: str, requested: Sequence[str] | None, available: Sequence[str]) -> tuple[str, ...]:
    rep = _report_def(report_type)
    visible = tuple(col for col in allowed_columns_for_role(object_type=str(rep.get("object_type")), role=role) if col in set(available))
    desired = tuple(str(c) for c in (requested or rep.get("selected_columns") or ()) if str(c) in set(visible))
    if desired:
        return desired
    return tuple(col for col in visible if col in set(rep.get("selected_columns") or ())) or visible


def _summary_rows(*, report_type: str, df: pd.DataFrame, scc_threshold: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [{"metric": "rows", "value": int(len(df))}]
    key = str(report_type or "").strip().lower()
    if key in {"animals_overview", "milk_quality_watchlist"}:
        rows.append({"metric": "animals", "value": int(df.get("animal_id", pd.Series(dtype=object)).nunique())})
        if "active_treatments" in df.columns:
            rows.append({"metric": "animals_with_active_treatments", "value": int((pd.to_numeric(df.get("active_treatments"), errors="coerce").fillna(0) > 0).sum())})
        if "latest_scc_cells_ml" in df.columns:
            rows.append({"metric": f"high_scc_ge_{int(scc_threshold)}", "value": int((pd.to_numeric(df.get("latest_scc_cells_ml"), errors="coerce") >= int(scc_threshold)).sum())})
    elif key == "cow_value_culling":
        rows.append({"metric": "animals", "value": int(df.get("animal_id", pd.Series(dtype=object)).nunique())})
        rows.append({"metric": "recommended_cull", "value": int((df.get("recommended_action_code", pd.Series(dtype=object)).astype(str).str.lower() == 'cull').sum())})
        rows.append({"metric": "negative_keep_vs_replace", "value": int((pd.to_numeric(df.get("delta_keep_vs_replace_rub"), errors="coerce") < 0).sum())})
    elif key == "groups_overview":
        rows.append({"metric": "total_headcount", "value": int(pd.to_numeric(df.get("headcount"), errors="coerce").fillna(0).sum())})
        util = pd.to_numeric(df.get("utilization_pct"), errors="coerce")
        rows.append({"metric": "avg_utilization_pct", "value": round(float(util.dropna().mean()), 1) if not util.dropna().empty else 0.0})
    elif key in {"events_recent", "repro_attention", "health_attention"}:
        rows.append({"metric": "animals", "value": int(df.get("animal_id", pd.Series(dtype=object)).nunique())})
        if "event_family" in df.columns:
            family_counts = df.get("event_family", pd.Series(dtype=object)).astype(str).value_counts().to_dict()
            for family, count in sorted(family_counts.items()):
                rows.append({"metric": f"family:{family}", "value": int(count)})
    return rows


def build_operational_report_snapshot(
    *,
    input_dir: Path,
    asof_date: date,
    role: str,
    report_type: str,
    filters: Mapping[str, Any] | None = None,
    selected_columns: Sequence[str] | None = None,
    sort_by: str | None = None,
    sort_dir: str | None = None,
    limit: int = 200,
    scc_threshold: int = DEFAULT_SCC_THRESHOLD,
) -> dict[str, Any]:
    rep = _report_def(report_type)
    role_norm = _role_key(role)
    df = _base_df(input_dir=Path(input_dir), asof_date=asof_date, object_type=str(rep.get("object_type")), scc_threshold=int(scc_threshold), report_type=report_type)
    flt = {str(k): v for k, v in dict(filters or {}).items()}
    df = _apply_report_filters(df, report_type=report_type, filters=flt, scc_threshold=int(scc_threshold))
    total_before_limit = int(len(df))
    df, sort_used, dir_used = _apply_sort(df, sort_by=sort_by or rep.get("sort_by"), sort_dir=sort_dir or rep.get("sort_dir"))
    if int(limit or 0) > 0:
        df = df.head(max(1, int(limit)))

    available = tuple(str(c) for c in df.columns if c not in {"event_date_ts", "object_type", "object_id", "open_target"})
    visible = tuple(col for col in allowed_columns_for_role(object_type=str(rep.get("object_type")), role=role_norm) if col in set(available))
    selected = _selected_columns(report_type=report_type, role=role_norm, requested=selected_columns, available=available)
    records = df.to_dict(orient="records") if not df.empty else []
    return {
        "report_type": str(report_type).strip().lower() or "animals_overview",
        "label": str(rep.get("label") or "Operational report"),
        "description": str(rep.get("description") or ""),
        "object_type": str(rep.get("object_type") or "animals"),
        "role": role_norm,
        "rows": records,
        "total_before_limit": total_before_limit,
        "returned_rows": len(records),
        "available_columns": available,
        "visible_columns": visible,
        "selected_columns": selected,
        "sort_by": sort_used,
        "sort_dir": dir_used,
        "filters": flt,
        "summary_rows": _summary_rows(report_type=report_type, df=df, scc_threshold=int(scc_threshold)),
        "formula_rows": [dict(row) for row in list(rep.get("formula_rows") or [])],
    }


def build_operational_report_table(snapshot: Mapping[str, Any]) -> pd.DataFrame:
    rows = list(snapshot.get("rows") or [])
    selected = [str(c) for c in (snapshot.get("selected_columns") or []) if str(c).strip()]
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=selected)
    cols = [c for c in selected if c in df.columns]
    return df[cols].copy() if cols else df.copy()


def export_operational_report(snapshot: Mapping[str, Any], *, fmt: str) -> bytes:
    table = build_operational_report_table(snapshot)
    kind = str(fmt or "csv").strip().lower()
    if kind == "xlsx":
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            table.to_excel(writer, sheet_name="report", index=False)
            pd.DataFrame(list(snapshot.get("summary_rows") or [])).to_excel(writer, sheet_name="summary", index=False)
            pd.DataFrame(list(snapshot.get("formula_rows") or [])).to_excel(writer, sheet_name="formulas", index=False)
        return buf.getvalue()
    return table.to_csv(index=False).encode("utf-8")


__all__ = [
    "DEFAULT_SCC_THRESHOLD",
    "REPORT_DEFS",
    "REPORT_TYPES",
    "build_operational_report_snapshot",
    "build_operational_report_table",
    "export_operational_report",
]

from __future__ import annotations

"""Director dashboard insights helpers (T10-02).

Offline-core module.

Provides:
- Top deviations (plan-fact vs targets) with explanations and lineage links.

The Web UI must not implement business logic; it should call functions from here.
"""

from typing import Any, Dict, List, Optional

from pathlib import Path

import yaml

import pandas as pd


class InsightsError(ValueError):
    """Human-readable errors in insights computation."""


def _kpi_label(kpi_def: Dict[str, Any], kpi_id: str) -> str:
    return str(kpi_def.get("title") or kpi_def.get("name") or kpi_id)


def _fmt_sources(kpi_def: Dict[str, Any]) -> str:
    sources = kpi_def.get("sources") or []
    if not isinstance(sources, list) or not sources:
        return ""
    parts: List[str] = []
    for s in sources:
        if not isinstance(s, dict):
            continue
        table = s.get("table")
        fields = s.get("fields") or []
        if not table:
            continue
        if isinstance(fields, list) and fields:
            # limit fields to keep the string short
            ff = ",".join(str(f) for f in fields[:12])
            parts.append(f"{table}({ff})")
        else:
            parts.append(str(table))
    return "; ".join(parts)


def _require_cols(df: pd.DataFrame, cols: List[str], *, ctx: str) -> None:
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise InsightsError(f"{ctx}: отсутствуют колонки {miss}. Доступно: {list(df.columns)[:25]}")


def compute_top_deviations(
    plan_fact: pd.DataFrame,
    *,
    kpi_cfg: Dict[str, Dict[str, Any]],
    top_n: int = 10,
) -> pd.DataFrame:
    """Return top deviations table with explanations.

    Expects plan_fact produced by genomeai.kpi_targets.compute_plan_fact.

    Output is safe to show in UI and can be exported as a mart.
    """

    out_cols = [
        "tenant_id",
        "farm_id",
        "site_id",
        "kpi_id",
        "kpi_name",
        "domain",
        "period_days",
        "sources",
        "actual_value",
        "target_value",
        "unit",
        "direction",
        "status",
        "delta",
        "delta_pct",
        "abs_delta_pct",
        "explanation",
        "data_version",
        "kpi_run_id",
        "targets_source",
        "kpi_artifact_relpath",
    ]

    if plan_fact is None or plan_fact.empty:
        return pd.DataFrame(columns=out_cols)

    _require_cols(
        plan_fact,
        [
            "tenant_id",
            "farm_id",
            "kpi_id",
            "actual_value",
            "target_value",
            "unit",
            "direction",
            "status",
            "delta",
            "delta_pct",
            "data_version",
            "kpi_run_id",
            "targets_source",
        ],
        ctx="plan_fact",
    )

    df = plan_fact.copy()
    if "site_id" not in df.columns:
        df["site_id"] = pd.NA

    df["delta_pct"] = pd.to_numeric(df["delta_pct"], errors="coerce")
    df["actual_value"] = pd.to_numeric(df["actual_value"], errors="coerce")
    df["target_value"] = pd.to_numeric(df["target_value"], errors="coerce")

    # Focus on actionable deviations.
    df = df.loc[df["status"].isin(["WARN", "ALERT"])].copy()
    df = df.loc[df["delta_pct"].notna()].copy()
    if df.empty:
        return pd.DataFrame(columns=out_cols)

    df.loc[:, "abs_delta_pct"] = df["delta_pct"].abs()
    df = df.sort_values(["status", "abs_delta_pct"], ascending=[True, False])
    df = df.head(int(top_n)).reset_index(drop=True)

    rows = []
    for _, r in df.iterrows():
        kid = str(r.get("kpi_id"))
        kdef = kpi_cfg.get(kid, {}) if isinstance(kpi_cfg, dict) else {}
        name = _kpi_label(kdef, kid)
        domain = str(kdef.get("domain") or "")
        period_days: Optional[int] = None
        try:
            if "period_days" in kdef and kdef.get("period_days") is not None:
                period_days = int(kdef.get("period_days"))
        except Exception:
            period_days = None
        sources = _fmt_sources(kdef)

        actual = r.get("actual_value")
        target = r.get("target_value")
        unit = str(r.get("unit") or "")
        status = str(r.get("status") or "")
        direction = str(r.get("direction") or "")
        delta = r.get("delta")
        dp = r.get("delta_pct")

        dv = str(r.get("data_version") or "")
        rid = str(r.get("kpi_run_id") or "")
        targets_source = str(r.get("targets_source") or "")
        kpi_art = f"{dv}/runs/{rid}/kpi/kpi_long.csv" if (dv and rid) else None

        # human-readable explanation (short, factual)
        try:
            dp_pct = float(dp) * 100.0
            dp_s = f"{dp_pct:+.1f}%"
        except Exception:
            dp_s = "NA"

        explanation_parts = [
            f"{name}: факт {actual} {unit} vs цель {target} {unit} (Δ={dp_s}, статус={status}).",
            f"Источник KPI: run_id={rid} (kpi_long.csv).",
            f"Цели/пороги: {targets_source}.",
        ]
        if sources:
            explanation_parts.insert(1, f"Данные KPI: {sources}.")
        explanation = " ".join(explanation_parts)

        rows.append(
            {
                "tenant_id": r.get("tenant_id"),
                "farm_id": r.get("farm_id"),
                "site_id": r.get("site_id"),
                "kpi_id": kid,
                "kpi_name": name,
                "domain": domain,
                "period_days": period_days,
                "sources": sources,
                "actual_value": actual,
                "target_value": target,
                "unit": unit,
                "direction": direction,
                "status": status,
                "delta": delta,
                "delta_pct": dp,
                "abs_delta_pct": float(abs(dp)) if pd.notna(dp) else pd.NA,
                "explanation": explanation,
                "data_version": dv,
                "kpi_run_id": rid,
                "targets_source": targets_source,
                "kpi_artifact_relpath": kpi_art,
            }
        )

    return pd.DataFrame(rows, columns=out_cols)


def load_trend_exceptions_rules(cfg_path: Path) -> dict:
    """Load rules for trend exceptions.

    Rules are stored in YAML and must have defaults.
    """
    defaults = {
        "top_n": 10,
        "warn_change_pct": 0.05,
        "alert_change_pct": 0.10,
        "min_prev_sum": 1.0,
        "windows": [7, 30, 90],
    }
    try:
        if cfg_path and Path(cfg_path).exists():
            d = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8")) or {}
            if isinstance(d, dict):
                defaults.update({k: v for k, v in d.items() if v is not None})
    except Exception:
        # fall back to defaults
        pass
    return defaults


def compute_milk_trend_exceptions(
    milk_windows: pd.DataFrame,
    *,
    rules: dict,
    data_version: str,
    dashboard_run_id: str,
) -> pd.DataFrame:
    """Compute top trend exceptions for milk windows.

    Input: output of genomeai.dashboard_director.compute_milk_trend_windows

    Output columns are safe to show in UI and export as mart.
    """
    out_cols = [
        "kpi_id",
        "window_days",
        "severity",
        "change_pct",
        "change_kg",
        "cur_sum_kg",
        "prev_sum_kg",
        "cur_start",
        "cur_end",
        "prev_start",
        "prev_end",
        "source_table",
        "source_path",
        "data_version",
        "dashboard_run_id",
        "windows_artifact_relpath",
        "exceptions_artifact_relpath",
        "explanation",
    ]

    if milk_windows is None or milk_windows.empty:
        return pd.DataFrame(columns=out_cols)

    _require_cols(
        milk_windows,
        [
            "window_days",
            "cur_sum_kg",
            "prev_sum_kg",
            "change_kg",
            "change_pct",
            "cur_start",
            "cur_end",
            "prev_start",
            "prev_end",
            "source_table",
            "source_path",
        ],
        ctx="milk_trend_windows",
    )

    r = rules or {}
    top_n = int(r.get("top_n", 10))
    warn_th = float(r.get("warn_change_pct", 0.05))
    alert_th = float(r.get("alert_change_pct", 0.10))
    min_prev = float(r.get("min_prev_sum", 1.0))

    df = milk_windows.copy()
    df["change_pct"] = pd.to_numeric(df["change_pct"], errors="coerce")
    df["prev_sum_kg"] = pd.to_numeric(df["prev_sum_kg"], errors="coerce")
    df["cur_sum_kg"] = pd.to_numeric(df["cur_sum_kg"], errors="coerce")
    df["change_kg"] = pd.to_numeric(df["change_kg"], errors="coerce")

    # Avoid noisy ratios when previous window is near zero.
    df = df.loc[df["prev_sum_kg"].fillna(0.0) >= min_prev].copy()
    df = df.loc[df["change_pct"].notna()].copy()
    if df.empty:
        return pd.DataFrame(columns=out_cols)

    df.loc[:, "abs_change_pct"] = df["change_pct"].abs()

    def _sev(x: float) -> str:
        ax = abs(float(x))
        if ax >= alert_th:
            return "ALERT"
        if ax >= warn_th:
            return "WARN"
        return "OK"

    df.loc[:, "severity"] = df["change_pct"].apply(_sev)
    df = df.loc[df["severity"].isin(["WARN", "ALERT"])].copy()
    if df.empty:
        return pd.DataFrame(columns=out_cols)

    # Rank: ALERT first, then larger absolute changes.
    sev_rank = {"ALERT": 0, "WARN": 1}
    df.loc[:, "_sev_rank"] = df["severity"].map(sev_rank).fillna(9).astype(int)
    df = df.sort_values(["_sev_rank", "abs_change_pct"], ascending=[True, False]).head(top_n)

    rows = []
    for _, rr in df.iterrows():
        w = int(rr.get("window_days"))
        cp = float(rr.get("change_pct"))
        ck = float(rr.get("change_kg"))
        cur = float(rr.get("cur_sum_kg"))
        prev = float(rr.get("prev_sum_kg"))
        sev = str(rr.get("severity"))

        cp_s = f"{cp*100:+.1f}%" if pd.notna(cp) else "NA"
        win_rel = (
            f"{data_version}/runs/{dashboard_run_id}/dashboards/director_summary/milk_trend_windows.csv"
            if (data_version and dashboard_run_id)
            else None
        )
        exc_rel = (
            f"{data_version}/runs/{dashboard_run_id}/dashboards/director_summary/milk_trend_exceptions.csv"
            if (data_version and dashboard_run_id)
            else None
        )
        expl = (
            f"Тренд молока ({w}d): текущее окно {cur:.0f} кг vs предыдущее {prev:.0f} кг "
            f"(Δ={ck:+.0f} кг, {cp_s}, severity={sev}). "
            f"Источник: {rr.get('source_table')} ({rr.get('source_path')}). "
            f"Артефакты: windows={win_rel}; exceptions={exc_rel}. "
            f"run_id={dashboard_run_id}, data_version={data_version}."
        )

        rows.append(
            {
                "kpi_id": "milk_kg_total",
                "window_days": w,
                "severity": sev,
                "change_pct": cp,
                "change_kg": ck,
                "cur_sum_kg": cur,
                "prev_sum_kg": prev,
                "cur_start": rr.get("cur_start"),
                "cur_end": rr.get("cur_end"),
                "prev_start": rr.get("prev_start"),
                "prev_end": rr.get("prev_end"),
                "source_table": rr.get("source_table"),
                "source_path": rr.get("source_path"),
                "data_version": data_version,
                "dashboard_run_id": dashboard_run_id,
                "windows_artifact_relpath": win_rel,
                "exceptions_artifact_relpath": exc_rel,
                "explanation": expl,
            }
        )

    return pd.DataFrame(rows, columns=out_cols)

from __future__ import annotations

import json
from datetime import date as _date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from core.reporting.fact_pack import build_regular_fact_pack
from genomeai.drilldown import kpi_breakdown_by_animal, kpi_breakdown_by_pen
from genomeai.economics_v2 import load_economics_v2


def _economics_snapshot_table(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    focus_type: str,
    focus_id: str,
    max_rows: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    meta: dict[str, Any] = {"available": False, "economics_run": "", "date_selected": "", "note": ""}
    try:
        rid, dfs, _ = load_economics_v2(artifacts_root=artifacts_root, data_version=str(data_version), economics_run=None)
    except Exception as e:
        meta["note"] = f"no economics_v2: {e}"
        return meta, pd.DataFrame()

    daily = dfs.get("economics_daily")
    if daily is None or daily.empty:
        meta.update({"available": False, "economics_run": rid, "note": "economics_daily пуст"})
        return meta, pd.DataFrame()

    df = daily.copy()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    try:
        ad = pd.to_datetime(asof_date, errors="coerce")
    except Exception:
        ad = pd.NaT
    if "date" in df.columns and not df["date"].isna().all():
        if pd.notna(ad):
            candidates = df[df["date"] <= ad]
            dsel = candidates["date"].max() if not candidates.empty else df["date"].max()
        else:
            dsel = df["date"].max()
        df = df[df["date"] == dsel].copy()
        meta["date_selected"] = str(getattr(dsel, "date", lambda: dsel)()) if hasattr(dsel, "date") else str(dsel)

    ft = (focus_type or "").strip().lower()
    fid = (focus_id or "").strip()

    if ft in {"group", "pen"} and fid and "level" in df.columns and "pen_id" in df.columns:
        df = df[(df["level"] == "pen") & (df["pen_id"].astype(str) == str(fid))].copy()
    elif ft == "farm" and fid and "level" in df.columns and "farm_id" in df.columns:
        df = df[(df["level"] == "farm") & (df["farm_id"].astype(str) == str(fid))].copy()
    elif ft == "site" and fid and "level" in df.columns and "site_id" in df.columns:
        df = df[(df["level"] == "site") & (df["site_id"].astype(str) == str(fid))].copy()
    else:
        if "level" in df.columns:
            df = df[df["level"] == "farm"].copy()

    keep = [
        c
        for c in [
            "date",
            "level",
            "farm_id",
            "site_id",
            "pen_id",
            "milk_liters",
            "revenue_total_rub",
            "total_cost_rub",
            "margin_rub",
            "margin_pct",
            "cost_per_liter_rub",
        ]
        if c in df.columns
    ]
    if keep:
        df = df[keep].copy()

    sort_cols = [c for c in ["farm_id", "site_id", "pen_id"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols)
    if len(df) > max_rows:
        df = df.head(max_rows)

    meta.update({"available": True, "economics_run": rid, "note": ""})
    return meta, df


def _safe_date(x: str) -> _date:
    try:
        return pd.to_datetime(x, errors="coerce").date()
    except Exception:
        return _date.today()


def _top_rows(records: List[dict], n: int = 20) -> List[dict]:
    out: List[dict] = []
    for r in records[:n]:
        if isinstance(r, dict):
            out.append(r)
    return out


def _kpi_table_from_artifacts(*, artifacts_root: Path, data_version: str, metrics: list[str]) -> pd.DataFrame:
    base = Path(artifacts_root) / str(data_version)
    candidates: list[Path] = []
    try:
        for p in base.rglob("kpi_wide.csv"):
            if p.is_file() and p.parent.name == "kpi":
                candidates.append(p)
    except Exception:
        candidates = []
    if not candidates:
        return pd.DataFrame(columns=["kpi_id", "value", "unit"])

    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    kpi_wide_path = candidates[-1]
    try:
        df = pd.read_csv(kpi_wide_path)
    except Exception:
        return pd.DataFrame(columns=["kpi_id", "value", "unit"])

    if df.empty:
        return pd.DataFrame(columns=["kpi_id", "value", "unit"])

    for c in ["kpi_id", "value"]:
        if c not in df.columns:
            return pd.DataFrame(columns=["kpi_id", "value", "unit"])
    if "unit" not in df.columns:
        df["unit"] = ""

    df["kpi_id"] = df["kpi_id"].astype(str)
    df = df.set_index("kpi_id")

    rows = []
    for mid in metrics:
        mid = str(mid)
        if mid in df.index:
            r = df.loc[mid]
            if isinstance(r, pd.DataFrame):
                r = r.iloc[0]
            rows.append({"kpi_id": mid, "value": r.get("value"), "unit": r.get("unit", "")})
        else:
            rows.append({"kpi_id": mid, "value": "NA", "unit": ""})
    return pd.DataFrame(rows)


def _md_table(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "NA"
    try:
        return df.to_markdown(index=False)
    except Exception:
        return df.head(50).to_csv(index=False)


def sanitize_template(template: dict[str, Any]) -> dict[str, Any]:
    return {
        "template_id": str(template.get("template_id") or ""),
        "name": str(template.get("name") or ""),
        "scope": str(template.get("scope") or "user"),
        "sections": list(template.get("sections") or []),
        "metrics": list(template.get("metrics") or []),
        "options": dict(template.get("options") or {}),
    }


def prepare_template_report_artifacts(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    report_version: str,
    out_dir: Path,
    exports_dir: Path,
    template: dict[str, Any],
    inputs: Optional[dict[str, Any]],
    mode: str,
    max_rows: int,
    options_override: Optional[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    _ = out_dir, exports_dir
    dv = str(data_version)
    tpl = sanitize_template(template or {})
    if options_override:
        opts = dict(tpl.get("options") or {})
        opts.update(dict(options_override or {}))
        tpl["options"] = opts

    focus_type = str((tpl.get("options") or {}).get("focus_type") or "").strip().lower()
    focus_id = str((tpl.get("options") or {}).get("focus_id") or "").strip()

    alerts_in: list[dict[str, Any]] = []
    tasks_in: list[dict[str, Any]] = []
    decisions_in: list[dict[str, Any]] = []

    def _expand_types(base: str) -> set[str]:
        b = (base or "").strip().lower()
        if b in {"group", "pen"}:
            return {"group", "pen"}
        if b in {"animal", "cow"}:
            return {"animal", "cow"}
        if b:
            return {b}
        return set()

    def _filter_by_object(records: list[dict[str, Any]], *, base_type: str, oid: str) -> list[dict[str, Any]]:
        types = _expand_types(base_type)
        if not types or not oid:
            return records
        out: list[dict[str, Any]] = []
        for r in records:
            if not isinstance(r, dict):
                continue
            rt = str(r.get("object_type") or "").strip().lower()
            rid = str(r.get("object_id") or "").strip()
            if (rt in types) and (rid == oid):
                out.append(r)
        return out

    def _filter_by_related_alert(records: list[dict[str, Any]], *, alert_id: str) -> list[dict[str, Any]]:
        if not alert_id:
            return records
        out: list[dict[str, Any]] = []
        for r in records:
            if not isinstance(r, dict):
                continue
            if str(r.get("related_alert") or "").strip() == str(alert_id).strip():
                out.append(r)
        return out

    if focus_type and focus_id and inputs:
        if focus_type == "alert":
            alerts_in = [a for a in (inputs.get("alerts") or []) if isinstance(a, dict) and str(a.get("alert_id") or "").strip() == focus_id]
            tasks_in = _filter_by_related_alert([t for t in (inputs.get("tasks") or []) if isinstance(t, dict)], alert_id=focus_id)
            decisions_in = _filter_by_related_alert([d for d in (inputs.get("decisions") or []) if isinstance(d, dict)], alert_id=focus_id)
        else:
            alerts_in = _filter_by_object([a for a in (inputs.get("alerts") or []) if isinstance(a, dict)], base_type=focus_type, oid=focus_id)
            tasks_in = _filter_by_object([t for t in (inputs.get("tasks") or []) if isinstance(t, dict)], base_type=focus_type, oid=focus_id)
            decisions_in = _filter_by_object([d for d in (inputs.get("decisions") or []) if isinstance(d, dict)], base_type=focus_type, oid=focus_id)
    elif inputs:
        alerts_in = [a for a in (inputs.get("alerts") or []) if isinstance(a, dict)]
        tasks_in = [t for t in (inputs.get("tasks") or []) if isinstance(t, dict)]
        decisions_in = [d for d in (inputs.get("decisions") or []) if isinstance(d, dict)]

    fact_pack = build_regular_fact_pack(
        artifacts_root=artifacts_root,
        data_version=dv,
        asof_date=str(asof_date),
        period="daily",
        max_rows=max_rows,
    )
    fact_pack.setdefault("versions", {})
    fact_pack["versions"]["data_version"] = dv
    fact_pack["versions"]["report_version"] = report_version
    fact_pack["template"] = tpl
    fact_pack["focus"] = {"focus_type": focus_type or "", "focus_id": focus_id or ""}

    fact_pack["web"] = {
        "alerts_top": _top_rows(alerts_in or [], n=max_rows),
        "tasks_top": _top_rows(tasks_in or [], n=max_rows),
        "decisions_top": _top_rows(decisions_in or [], n=max_rows),
    }

    econ_meta, econ_df = _economics_snapshot_table(
        artifacts_root=artifacts_root,
        data_version=dv,
        asof_date=str(asof_date),
        focus_type=focus_type,
        focus_id=focus_id,
        max_rows=max_rows,
    )
    fact_pack["economics_v2"] = {
        "available": bool(econ_meta.get("available")),
        "economics_run": str(econ_meta.get("economics_run") or ""),
        "date_selected": str(econ_meta.get("date_selected") or ""),
        "note": str(econ_meta.get("note") or ""),
        "snapshot_top": json.loads(econ_df.fillna("").to_json(orient="records", force_ascii=False)) if (econ_df is not None and not econ_df.empty) else [],
    }

    metric0 = (tpl.get("metrics") or ["milk_total_kg_7d"])[0]
    try:
        asof_dt = _safe_date(str(asof_date))

        pen_filter: Optional[str] = None
        animal_filter: Optional[str] = None
        if focus_type in {"group", "pen"} and focus_id:
            pen_filter = focus_id
        if focus_type in {"animal", "cow"} and focus_id:
            animal_filter = focus_id

        pen_df = kpi_breakdown_by_pen(
            artifacts_dir=artifacts_root,
            data_version=dv,
            kpi_id=str(metric0),
            asof_date=asof_dt,
        )

        ani_df = kpi_breakdown_by_animal(
            artifacts_dir=artifacts_root,
            data_version=dv,
            kpi_id=str(metric0),
            asof_date=asof_dt,
            pen_id=pen_filter,
        )

        if animal_filter and not ani_df.empty:
            if "animal_id" in ani_df.columns:
                ani_df = ani_df[ani_df["animal_id"].astype(str) == str(animal_filter)].copy()
            if pen_filter is None and ("pen_id" in ani_df.columns) and (not ani_df.empty):
                pen_filter = str(ani_df.iloc[0].get("pen_id") or "") or None

        if pen_filter and not pen_df.empty and "pen_id" in pen_df.columns:
            pen_df = pen_df[pen_df["pen_id"].astype(str) == str(pen_filter)].copy()

        if not pen_df.empty and "value" in pen_df.columns:
            pen_df = pen_df.sort_values(["value"], ascending=[False]).head(max_rows)
        if not ani_df.empty and "value" in ani_df.columns:
            ani_df = ani_df.sort_values(["value"], ascending=[False]).head(max_rows)

        fact_pack["top_groups"] = json.loads(pen_df.fillna("").to_json(orient="records", force_ascii=False)) if not pen_df.empty else []
        fact_pack["top_animals"] = json.loads(ani_df.fillna("").to_json(orient="records", force_ascii=False)) if not ani_df.empty else []
    except Exception:
        fact_pack["top_groups"] = []
        fact_pack["top_animals"] = []

    sections = set([str(s) for s in (tpl.get("sections") or [])])
    metrics = [str(m) for m in (tpl.get("metrics") or [])]
    if not metrics:
        metrics = ["milk_total_kg_7d"]

    lines: List[str] = []
    lines.append(f"# Template report: {tpl.get('name') or 'NA'}")
    lines.append(f"report_version: {report_version}")
    lines.append(f"data_version: {dv}")
    lines.append(f"asof_date: {asof_date}")
    lines.append(f"template_id: {tpl.get('template_id') or 'NA'}")
    if focus_type and focus_id:
        lines.append(f"focus: {focus_type}:{focus_id}")
    lines.append("---")
    lines.append("")

    if "kpi_summary" in sections:
        lines.append("## KPI summary")
        kdf = _kpi_table_from_artifacts(artifacts_root=artifacts_root, data_version=dv, metrics=metrics)
        lines.append(_md_table(kdf))
        lines.append("")

    if "alerts" in sections:
        lines.append("## Alerts (top)")
        a = alerts_in or []
        if not a:
            lines.append("NA")
        else:
            adf = pd.DataFrame(_top_rows(a, n=max_rows))
            keep = [c for c in ["alert_id", "title", "status", "severity", "created_at", "updated_at", "run_id", "data_version"] if c in adf.columns]
            if keep:
                adf = adf[keep]
            lines.append(_md_table(adf))
        lines.append("")

    if "decisions" in sections:
        lines.append("## Decisions (top)")
        d = decisions_in or []
        if not d:
            lines.append("NA")
        else:
            ddf = pd.DataFrame(_top_rows(d, n=max_rows))
            keep = [c for c in ["decision_id", "title", "status", "created_at", "updated_at", "object_type", "object_id", "run_id", "data_version"] if c in ddf.columns]
            if keep:
                ddf = ddf[keep]
            lines.append(_md_table(ddf))
        lines.append("")

    if "tasks" in sections:
        lines.append("## Tasks (top)")
        t = tasks_in or []
        if not t:
            lines.append("NA")
        else:
            tdf = pd.DataFrame(_top_rows(t, n=max_rows))
            keep = [c for c in ["task_id", "title", "status", "priority", "due_at", "owner_user_id", "object_type", "object_id", "run_id", "data_version"] if c in tdf.columns]
            if keep:
                tdf = tdf[keep]
            lines.append(_md_table(tdf))
        lines.append("")

    if "groups" in sections:
        lines.append(f"## Groups top by {metric0}")
        g = fact_pack.get("top_groups") or []
        if not g:
            lines.append("NA")
        else:
            gdf = pd.DataFrame(g)
            keep = [c for c in ["pen_name", "pen_id", "value", "unit", "animals_n"] if c in gdf.columns]
            if keep:
                gdf = gdf[keep]
            lines.append(_md_table(gdf))
        lines.append("")

    if "animals" in sections:
        lines.append(f"## Animals top by {metric0}")
        a = fact_pack.get("top_animals") or []
        if not a:
            lines.append("NA")
        else:
            adf = pd.DataFrame(a)
            keep = [c for c in ["animal_id", "pen_name", "pen_id", "value", "unit"] if c in adf.columns]
            if keep:
                adf = adf[keep]
            lines.append(_md_table(adf))
        lines.append("")

    if "economics" in sections:
        lines.append("## Economics (₽, economics_v2)")
        econ = fact_pack.get("economics_v2") or {}
        if not econ.get("available"):
            note = str(econ.get("note") or "Нет данных economics_v2")
            lines.append(f"NA ({note})")
        else:
            lines.append(f"economics_run: {econ.get('economics_run')}")
            if econ.get("date_selected"):
                lines.append(f"date_selected: {econ.get('date_selected')}")
            sdf = pd.DataFrame(econ.get("snapshot_top") or [])
            lines.append(_md_table(sdf))
        lines.append("")

    lines.append("---")
    lines.append("## Trace")
    lines.append("```json")
    lines.append(
        json.dumps(
            {
                "template": tpl,
                "mode": mode,
                "economics_v2": {
                    "available": bool((fact_pack.get("economics_v2") or {}).get("available")),
                    "economics_run": str((fact_pack.get("economics_v2") or {}).get("economics_run") or ""),
                    "date_selected": str((fact_pack.get("economics_v2") or {}).get("date_selected") or ""),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    lines.append("```")

    md_text = "\n".join(lines) + "\n"
    markdown_by_audience = {"director": md_text, "ops": md_text}
    summary_inputs = {
        "template": tpl,
        "focus": {"focus_type": focus_type or "", "focus_id": focus_id or ""},
        "input_counts": {
            "alerts": len(alerts_in or []),
            "tasks": len(tasks_in or []),
            "decisions": len(decisions_in or []),
        },
    }
    return fact_pack, markdown_by_audience, summary_inputs


__all__ = ["prepare_template_report_artifacts", "sanitize_template"]

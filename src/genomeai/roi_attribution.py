from core.infra.postgres_compat import connect_postgres_compat as _pg_connect
from __future__ import annotations

"""T11-03: ROI панель — эффект от решений/задач (до/после, attribution).

Важное:
- ROI считается в offline-core и сохраняется как витрина (UI только запускает и читает артефакты).
- Основа эффекта: маржа (margin_rub) из unit_economics_*_daily (доход - расход).
- Источники действий:
  * decision_log.csv (legacy offline)
  * web.db: decision_log_v2 + tasks_v1 (done)

Методы attribution (cfg.roi.method):
- before_after: сравнение маржи до/после вокруг даты действия.
- diff_in_diff (animal-only): difference-in-differences с контрольной группой в scope (pen/site/farm).
  При невозможности подобрать контроль (мало животных/плохое покрытие) — fallback на before_after.

Артефакты:
  artifacts/<data_version>/roi/<roi_run>/
    - roi_actions.csv
    - roi_summary.csv
    - manifest.json
  + копия в Target run layout:
  artifacts/<data_version>/runs/<roi_run>/roi/

"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from .economics_v2 import load_economics_v2
from .unit_economics import load_unit_economics
from .versioning import (
    ensure_run_dir,
    generate_run_id,
    write_checksums,
    write_json,
    write_run_manifest,
)

DEFAULT_CFG_PATH = Path("configs/economics/roi_attribution_v1.yaml")


DETAIL_COMPONENT_COLS: list[str] = [
    "revenue_milk_rub",
    "revenue_cull_rub",
    "revenue_total_rub",
    "cost_feed_rub",
    "cost_other_rub",
    "cost_vet_rub",
    "cost_repro_rub",
    "cost_cull_rub",
    "total_cost_rub",
    "margin_rub",
]


DETAIL_SERIES_COLS: list[str] = [
    "revenue_total_rub",
    "total_cost_rub",
    "margin_rub",
]


QUALITY_REASON_MAP: dict[str, str] = {
    "LOW_COVERAGE": "Недостаточное покрытие данных в окнах до/после (мало дней в unit_economics)",
    "NO_CONTROL_GROUP": "Недостаточно объектов контроля для diff-in-diff (fallback на before/after)",
    "LOW_CONTROL_COVERAGE": "Недостаточное покрытие данных в контрольной группе (fallback на before/after)",
    "COST_UNKNOWN": "Стоимость действия не найдена по cost_mapping/cost_models (cost=0)",
    "MISSING_SERIES": "Нет рядов unit_economics для объекта (series пуст)",
}


def _utc_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_cfg(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore

        obj = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
        return obj or {}
    except Exception:
        return {}


def _norm_date(s: Any) -> Optional[pd.Timestamp]:
    try:
        ts = pd.to_datetime(s, errors="coerce", utc=True)
        if pd.isna(ts):
            return None
        return ts.tz_convert(None).normalize()
    except Exception:
        try:
            ts = pd.to_datetime(s, errors="coerce")
            if pd.isna(ts):
                return None
            return ts.normalize()
        except Exception:
            return None


def _normalize_object_type(t: str | None) -> str:
    tt = (t or "").strip().lower()
    if not tt:
        return "unknown"
    if tt in {"cow", "animal", "cattle"}:
        return "animal"
    if tt in {"pen", "group", "stall", "barn"}:
        return "pen"
    if tt in {"site", "yard"}:
        return "site"
    if tt in {"farm"}:
        return "farm"
    return tt


def _read_decision_log_csv(artifacts_root: Path, data_version: str) -> pd.DataFrame:
    p = Path(artifacts_root) / data_version / "decisions" / "decision_log.csv"
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(p)
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df

    df["source"] = "decision_log_csv"
    df["source_id"] = df.index.astype(str)
    df["object_type"] = "animal"
    df["object_id"] = df.get("animal_id").astype(str)
    df["action_type"] = df.get("recommendation_type").astype(str)
    df["action_date"] = df.get("created_at_utc").apply(_norm_date)
    df["comment"] = df.get("comment")
    df["status_raw"] = df.get("decision")

    # best-effort versions
    df["scoring_run"] = df.get("scoring_run")
    df["qc_run"] = ""
    df["model_version"] = ""
    df["report_version"] = ""
    return df


def _read_web_db_actions(web_db_path: Path, tenant_id: str) -> pd.DataFrame:
    if not web_db_path or not Path(web_db_path).exists():
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    conn = _pg_connect())
    try:
        # decisions v2
        try:
            dec = conn.execute(
                "SELECT * FROM decision_log_v2 WHERE tenant_id=? ORDER BY created_at DESC LIMIT 5000",
                (tenant_id,),
            ).fetchall()
            for r in dec:
                d = dict(r)
                rows.append(
                    {
                        "source": "web_db.decision_log_v2",
                        "source_id": str(d.get("decision_id") or d.get("id")),
                        "object_type": _normalize_object_type(d.get("object_type")),
                        "object_id": str(d.get("object_id") or ""),
                        "action_type": str(d.get("action") or ""),
                        "action_date": _norm_date(d.get("created_at")),
                        "comment": str(d.get("comment") or ""),
                        "reason": str(d.get("reason") or ""),
                        "data_version": str(d.get("data_version") or ""),
                        "qc_run": str(d.get("qc_run") or ""),
                        "model_version": str(d.get("model_version") or ""),
                        "scoring_run": str(d.get("scoring_run") or ""),
                        "report_version": str(d.get("report_version") or ""),
                        "status_raw": str(d.get("action") or ""),
                    }
                )
        except Exception:
            pass

        # tasks v1 (only done)
        try:
            trows = conn.execute(
                """
                SELECT * FROM tasks_v1
                WHERE tenant_id=? AND status='done'
                ORDER BY COALESCE(closed_at, updated_at) DESC
                LIMIT 5000
                """,
                (tenant_id,),
            ).fetchall()
            for r in trows:
                d = dict(r)
                closed_at = d.get("closed_at") or d.get("updated_at")
                rows.append(
                    {
                        "source": "web_db.tasks_v1",
                        "source_id": str(d.get("task_id") or d.get("id")),
                        "object_type": _normalize_object_type(d.get("object_type")),
                        "object_id": str(d.get("object_id") or ""),
                        "action_type": str(d.get("task_type") or ""),
                        "action_date": _norm_date(closed_at),
                        "comment": str(d.get("closed_comment") or d.get("title") or ""),
                        "reason": str(d.get("closed_reason") or ""),
                        "data_version": str(d.get("data_version") or ""),
                        "qc_run": str(d.get("qc_run") or ""),
                        "model_version": str(d.get("model_version") or ""),
                        "scoring_run": str(d.get("scoring_run") or ""),
                        "report_version": str(d.get("report_version") or ""),
                        "status_raw": "done",
                    }
                )
        except Exception:
            pass
    finally:
        conn.close()

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["object_id"] = df.get("object_id").astype(str)
    df = df[df["object_id"].astype(str) != ""].copy()
    return df


def _is_accepted(v: Any, accepted: set[str]) -> bool:
    s = str(v or "").strip().lower()
    return s in accepted


def _load_cost_models(artifacts_root: Path, data_version: str, economics_run: str) -> dict[str, float]:
    try:
        _, _, econ_run_dir = load_economics_v2(
            artifacts_root=artifacts_root,
            data_version=data_version,
            economics_run=economics_run,
        )
        p = Path(econ_run_dir) / "formulas_catalog.json"
        if not p.exists():
            return {}
        obj = json.loads(p.read_text(encoding="utf-8"))
        cm = (obj or {}).get("cost_models") or {}
        out: dict[str, float] = {}
        for k, v in cm.items():
            try:
                out[str(k)] = float(v)
            except Exception:
                continue
        return out
    except Exception:
        return {}


def _map_action_cost(action_type: str, mapping_rules: list[dict[str, Any]], cost_models: dict[str, float]) -> Tuple[float, str]:
    at = (action_type or "").strip().lower()
    for r in mapping_rules:
        words = [str(x).lower() for x in (r.get("match_any") or [])]
        if not words:
            continue
        if any(w in at for w in words):
            param = str(r.get("cost_param") or "")
            if not param:
                return 0.0, ""
            try:
                return float(cost_models.get(param) or 0.0), param
            except Exception:
                return 0.0, param
    return 0.0, ""


def _select_series(*, animal_daily: pd.DataFrame, group_daily: pd.DataFrame, object_type: str, object_id: str) -> pd.DataFrame:
    ot = _normalize_object_type(object_type)
    oid = str(object_id)

    if ot == "animal":
        df = animal_daily.copy()
        if df.empty:
            return df
        return df[df.get("animal_id").astype(str) == oid].copy()

    gd = group_daily.copy()
    if gd.empty:
        return gd

    if ot in {"pen", "group"}:
        gd = gd[gd.get("level").astype(str) == "pen"].copy()
        return gd[gd.get("pen_id").astype(str) == oid].copy()

    if ot == "site":
        gd = gd[gd.get("level").astype(str) == "site"].copy()
        return gd[gd.get("site_id").astype(str) == oid].copy()

    if ot == "farm":
        gd = gd[gd.get("level").astype(str) == "farm"].copy()
        return gd[gd.get("farm_id").astype(str) == oid].copy()

    return pd.DataFrame()


def _window_bounds(action_date: pd.Timestamp, window_days: int, include_action_day: bool) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]:
    ad = pd.to_datetime(action_date).normalize()
    if include_action_day:
        before_end = ad
        after_start = ad
    else:
        before_end = ad - pd.Timedelta(days=1)
        after_start = ad + pd.Timedelta(days=1)

    before_start = before_end - pd.Timedelta(days=window_days - 1)
    after_end = after_start + pd.Timedelta(days=window_days - 1)
    return before_start, before_end, after_start, after_end


def _compute_before_after(*, series: pd.DataFrame, action_date: pd.Timestamp, window_days: int, include_action_day: bool) -> dict[str, Any]:
    if series.empty or "date" not in series.columns:
        return {
            "before_days": 0,
            "after_days": 0,
            "before_sum": 0.0,
            "after_sum": 0.0,
            "before_avg": 0.0,
            "after_avg": 0.0,
            "delta_per_day": 0.0,
            "delta_window": 0.0,
        }

    df = series.copy()
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce").dt.normalize()
    df["margin_rub"] = pd.to_numeric(df.get("margin_rub"), errors="coerce").fillna(0.0)

    before_start, before_end, after_start, after_end = _window_bounds(action_date, window_days, include_action_day)

    before = df[(df["date"] >= before_start) & (df["date"] <= before_end)].copy()
    after = df[(df["date"] >= after_start) & (df["date"] <= after_end)].copy()

    b_days = int(before["date"].nunique()) if not before.empty else 0
    a_days = int(after["date"].nunique()) if not after.empty else 0
    b_sum = float(before["margin_rub"].sum()) if not before.empty else 0.0
    a_sum = float(after["margin_rub"].sum()) if not after.empty else 0.0

    b_avg = b_sum / max(b_days, 1)
    a_avg = a_sum / max(a_days, 1)
    delta_per_day = a_avg - b_avg
    delta_window = delta_per_day * float(window_days)

    return {
        "before_days": b_days,
        "after_days": a_days,
        "before_sum": b_sum,
        "after_sum": a_sum,
        "before_avg": b_avg,
        "after_avg": a_avg,
        "delta_per_day": float(delta_per_day),
        "delta_window": float(delta_window),
    }


def _animal_scope_ids(animal_daily: pd.DataFrame, animal_id: str, action_date: pd.Timestamp) -> dict[str, str]:
    """Best-effort: pen/site/farm for animal around action_date using unit_economics animal_daily."""
    if animal_daily.empty:
        return {"pen_id": "", "site_id": "", "farm_id": ""}

    df = animal_daily[animal_daily.get("animal_id").astype(str) == str(animal_id)].copy()
    if df.empty or "date" not in df.columns:
        return {"pen_id": "", "site_id": "", "farm_id": ""}

    df["date"] = pd.to_datetime(df.get("date"), errors="coerce").dt.normalize()
    df = df.dropna(subset=["date"]).sort_values("date")
    if df.empty:
        return {"pen_id": "", "site_id": "", "farm_id": ""}

    ad = pd.to_datetime(action_date).normalize()
    left = df[df["date"] <= ad]
    row = left.iloc[-1] if not left.empty else df.iloc[0]

    out: dict[str, str] = {}
    for k in ["pen_id", "site_id", "farm_id"]:
        try:
            out[k] = str(row.get(k) or "")
        except Exception:
            out[k] = ""
    return out


def _control_candidates(
    *,
    animal_daily: pd.DataFrame,
    scope: str,
    scope_ids: dict[str, str],
    action_date: pd.Timestamp,
    treated_animal_id: str,
) -> list[str]:
    """Candidates on action_date within scope (pen/site/farm)."""
    if animal_daily.empty:
        return []
    df = animal_daily.copy()
    if "date" not in df.columns:
        return []

    df["date"] = pd.to_datetime(df.get("date"), errors="coerce").dt.normalize()
    ad = pd.to_datetime(action_date).normalize()
    df = df[df["date"] == ad].copy()
    if df.empty:
        return []

    scope = (scope or "pen").strip().lower()
    if scope == "pen":
        key = "pen_id"
    elif scope == "site":
        key = "site_id"
    elif scope == "farm":
        key = "farm_id"
    else:
        key = "pen_id"

    sid = str(scope_ids.get(key) or "")
    if not sid or key not in df.columns:
        return []

    cand = df[df.get(key).astype(str) == sid].get("animal_id")
    if cand is None:
        return []

    ids = [str(x) for x in cand.astype(str).unique().tolist() if str(x) and str(x) != str(treated_animal_id)]
    return ids


def _filter_controls_by_actions(
    *,
    candidates: list[str],
    actions_df: pd.DataFrame,
    before_start: pd.Timestamp,
    after_end: pd.Timestamp,
    action_type: str,
    exclude_any: bool,
    exclude_same_type: bool,
) -> list[str]:
    return _filter_controls_by_actions_generic(
        candidates=candidates,
        actions_df=actions_df,
        before_start=before_start,
        after_end=after_end,
        action_type=action_type,
        object_type="animal",
        exclude_any=exclude_any,
        exclude_same_type=exclude_same_type,
    )


def _filter_controls_by_actions_generic(
    *,
    candidates: list[str],
    actions_df: pd.DataFrame,
    before_start: pd.Timestamp,
    after_end: pd.Timestamp,
    action_type: str,
    object_type: str,
    exclude_any: bool,
    exclude_same_type: bool,
) -> list[str]:
    """Exclude control objects that have actions in the evaluation window."""
    if not candidates:
        return []
    if actions_df.empty:
        return candidates

    ot = _normalize_object_type(object_type)
    a = actions_df.copy()
    a = a[(a.get("object_type").astype(str) == ot)].copy()
    if a.empty:
        return candidates

    a["action_date"] = pd.to_datetime(a.get("action_date"), errors="coerce").dt.normalize()
    a = a.dropna(subset=["action_date"]).copy()
    a = a[(a["action_date"] >= before_start) & (a["action_date"] <= after_end)].copy()
    if a.empty:
        return candidates

    excl: set[str] = set()
    if exclude_any:
        excl |= set(a.get("object_id").astype(str).tolist())
    if exclude_same_type:
        at = str(action_type or "").strip().lower()
        same = a[a.get("action_type").astype(str).str.lower() == at]
        if not same.empty:
            excl |= set(same.get("object_id").astype(str).tolist())

    return [x for x in candidates if x not in excl]


def _group_scope_ids(group_daily: pd.DataFrame, object_type: str, object_id: str, action_date: pd.Timestamp) -> dict[str, str]:
    """Best-effort: site/farm for pen, farm for site around action_date using unit_economics group_daily."""
    if group_daily.empty or "date" not in group_daily.columns:
        return {"site_id": "", "farm_id": ""}

    ot = _normalize_object_type(object_type)
    oid = str(object_id)
    df = group_daily.copy()
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce").dt.normalize()
    df = df.dropna(subset=["date"]).sort_values("date")
    ad = pd.to_datetime(action_date).normalize()

    if ot == "pen":
        df = df[df.get("level").astype(str) == "pen"].copy()
        df = df[df.get("pen_id").astype(str) == oid].copy()
        if df.empty:
            return {"site_id": "", "farm_id": ""}
        left = df[df["date"] <= ad]
        row = left.iloc[-1] if not left.empty else df.iloc[0]
        return {"site_id": str(row.get("site_id") or ""), "farm_id": str(row.get("farm_id") or "")}

    if ot == "site":
        df = df[df.get("level").astype(str) == "site"].copy()
        df = df[df.get("site_id").astype(str) == oid].copy()
        if df.empty:
            return {"site_id": oid, "farm_id": ""}
        left = df[df["date"] <= ad]
        row = left.iloc[-1] if not left.empty else df.iloc[0]
        return {"site_id": oid, "farm_id": str(row.get("farm_id") or "")}

    return {"site_id": "", "farm_id": ""}


def _group_control_candidates(
    *,
    group_daily: pd.DataFrame,
    object_type: str,
    control_scope: str,
    scope_ids: dict[str, str],
    action_date: pd.Timestamp,
    treated_object_id: str,
) -> list[str]:
    """Candidates for group DiD on action_date within scope.

    Supported:
      - treated pen -> control pens in same site/farm
      - treated site -> control sites in same farm
    """
    if group_daily.empty or "date" not in group_daily.columns:
        return []

    ot = _normalize_object_type(object_type)
    df = group_daily.copy()
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce").dt.normalize()
    ad = pd.to_datetime(action_date).normalize()
    df = df[df["date"] == ad].copy()
    if df.empty:
        return []

    cs = (control_scope or "").strip().lower()

    if ot == "pen":
        df = df[df.get("level").astype(str) == "pen"].copy()
        if cs not in {"site", "farm"}:
            cs = "site"
        key = "site_id" if cs == "site" else "farm_id"
        sid = str(scope_ids.get(key) or "")
        if not sid or key not in df.columns:
            return []
        cand = df[df.get(key).astype(str) == sid].get("pen_id")
        if cand is None:
            return []
        ids = [str(x) for x in cand.astype(str).unique().tolist() if str(x) and str(x) != str(treated_object_id)]
        return ids

    if ot == "site":
        df = df[df.get("level").astype(str) == "site"].copy()
        if cs != "farm":
            cs = "farm"
        fid = str(scope_ids.get("farm_id") or "")
        if not fid or "farm_id" not in df.columns:
            return []
        cand = df[df.get("farm_id").astype(str) == fid].get("site_id")
        if cand is None:
            return []
        ids = [str(x) for x in cand.astype(str).unique().tolist() if str(x) and str(x) != str(treated_object_id)]
        return ids

    return []


def _compute_control_deltas_group(
    *,
    group_daily: pd.DataFrame,
    object_type: str,
    control_ids: list[str],
    before_start: pd.Timestamp,
    before_end: pd.Timestamp,
    after_start: pd.Timestamp,
    after_end: pd.Timestamp,
    window_days: int,
) -> dict[str, Any]:
    if not control_ids or group_daily.empty or "date" not in group_daily.columns:
        return {
            "control_n": int(len(control_ids)),
            "control_n_effective": 0,
            "control_before_avg": 0.0,
            "control_after_avg": 0.0,
            "control_delta_per_day": 0.0,
            "control_delta_window": 0.0,
            "control_cov_before": 0.0,
            "control_cov_after": 0.0,
        }

    ot = _normalize_object_type(object_type)
    if ot == "pen":
        level = "pen"
        id_col = "pen_id"
    elif ot == "site":
        level = "site"
        id_col = "site_id"
    else:
        return {
            "control_n": int(len(control_ids)),
            "control_n_effective": 0,
            "control_before_avg": 0.0,
            "control_after_avg": 0.0,
            "control_delta_per_day": 0.0,
            "control_delta_window": 0.0,
            "control_cov_before": 0.0,
            "control_cov_after": 0.0,
        }

    df = group_daily.copy()
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce").dt.normalize()
    df["margin_rub"] = pd.to_numeric(df.get("margin_rub"), errors="coerce").fillna(0.0)
    df = df[df.get("level").astype(str) == level].copy()
    df = df[df.get(id_col).astype(str).isin([str(x) for x in control_ids])].copy()
    df = df.dropna(subset=["date"])  # type: ignore

    if df.empty:
        return {
            "control_n": int(len(control_ids)),
            "control_n_effective": 0,
            "control_before_avg": 0.0,
            "control_after_avg": 0.0,
            "control_delta_per_day": 0.0,
            "control_delta_window": 0.0,
            "control_cov_before": 0.0,
            "control_cov_after": 0.0,
        }

    b = df[(df["date"] >= before_start) & (df["date"] <= before_end)].copy()
    a = df[(df["date"] >= after_start) & (df["date"] <= after_end)].copy()

    bstats = (
        b.groupby(id_col, dropna=False)
        .agg(before_sum=("margin_rub", "sum"), before_days=("date", "nunique"))
        .reset_index()
    )
    astats = (
        a.groupby(id_col, dropna=False)
        .agg(after_sum=("margin_rub", "sum"), after_days=("date", "nunique"))
        .reset_index()
    )

    m = bstats.merge(astats, on=id_col, how="outer")
    m["before_sum"] = pd.to_numeric(m.get("before_sum"), errors="coerce").fillna(0.0)
    m["after_sum"] = pd.to_numeric(m.get("after_sum"), errors="coerce").fillna(0.0)
    m["before_days"] = pd.to_numeric(m.get("before_days"), errors="coerce").fillna(0).astype(int)
    m["after_days"] = pd.to_numeric(m.get("after_days"), errors="coerce").fillna(0).astype(int)

    m["before_avg"] = m["before_sum"] / m["before_days"].clip(lower=1)
    m["after_avg"] = m["after_sum"] / m["after_days"].clip(lower=1)

    effective = m[(m["before_days"] > 0) & (m["after_days"] > 0)].copy()
    n_eff = int(len(effective))
    if n_eff == 0:
        return {
            "control_n": int(len(control_ids)),
            "control_n_effective": 0,
            "control_before_avg": 0.0,
            "control_after_avg": 0.0,
            "control_delta_per_day": 0.0,
            "control_delta_window": 0.0,
            "control_cov_before": float(m["before_days"].mean() / max(window_days, 1)) if len(m) else 0.0,
            "control_cov_after": float(m["after_days"].mean() / max(window_days, 1)) if len(m) else 0.0,
        }

    cb = float(effective["before_avg"].mean())
    ca_ = float(effective["after_avg"].mean())
    dd = ca_ - cb
    dw = dd * float(window_days)
    cov_b = float(effective["before_days"].mean() / max(window_days, 1))
    cov_a = float(effective["after_days"].mean() / max(window_days, 1))
    return {
        "control_n": int(len(control_ids)),
        "control_n_effective": n_eff,
        "control_before_avg": cb,
        "control_after_avg": ca_,
        "control_delta_per_day": float(dd),
        "control_delta_window": float(dw),
        "control_cov_before": cov_b,
        "control_cov_after": cov_a,
    }


def _compute_control_deltas(
    *,
    animal_daily: pd.DataFrame,
    control_animals: list[str],
    before_start: pd.Timestamp,
    before_end: pd.Timestamp,
    after_start: pd.Timestamp,
    after_end: pd.Timestamp,
    window_days: int,
) -> dict[str, Any]:
    if not control_animals or animal_daily.empty:
        return {
            "control_n": 0,
            "control_n_effective": 0,
            "control_before_avg": 0.0,
            "control_after_avg": 0.0,
            "control_delta_per_day": 0.0,
            "control_delta_window": 0.0,
            "control_cov_before": 0.0,
            "control_cov_after": 0.0,
        }

    df = animal_daily.copy()
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce").dt.normalize()
    df["margin_rub"] = pd.to_numeric(df.get("margin_rub"), errors="coerce").fillna(0.0)
    df = df[df.get("animal_id").astype(str).isin([str(x) for x in control_animals])].copy()
    df = df.dropna(subset=["date"])  # type: ignore

    if df.empty:
        return {
            "control_n": int(len(control_animals)),
            "control_n_effective": 0,
            "control_before_avg": 0.0,
            "control_after_avg": 0.0,
            "control_delta_per_day": 0.0,
            "control_delta_window": 0.0,
            "control_cov_before": 0.0,
            "control_cov_after": 0.0,
        }

    # before window per animal
    b = df[(df["date"] >= before_start) & (df["date"] <= before_end)].copy()
    a = df[(df["date"] >= after_start) & (df["date"] <= after_end)].copy()

    bstats = (
        b.groupby("animal_id", dropna=False)
        .agg(before_sum=("margin_rub", "sum"), before_days=("date", "nunique"))
        .reset_index()
    )
    astats = (
        a.groupby("animal_id", dropna=False)
        .agg(after_sum=("margin_rub", "sum"), after_days=("date", "nunique"))
        .reset_index()
    )

    m = bstats.merge(astats, on="animal_id", how="outer")
    m["before_sum"] = pd.to_numeric(m.get("before_sum"), errors="coerce").fillna(0.0)
    m["after_sum"] = pd.to_numeric(m.get("after_sum"), errors="coerce").fillna(0.0)
    m["before_days"] = pd.to_numeric(m.get("before_days"), errors="coerce").fillna(0).astype(int)
    m["after_days"] = pd.to_numeric(m.get("after_days"), errors="coerce").fillna(0).astype(int)

    # per animal averages
    m["before_avg"] = m["before_sum"] / m["before_days"].clip(lower=1)
    m["after_avg"] = m["after_sum"] / m["after_days"].clip(lower=1)

    effective = m[(m["before_days"] > 0) & (m["after_days"] > 0)].copy()
    n_eff = int(len(effective))

    if n_eff == 0:
        return {
            "control_n": int(len(control_animals)),
            "control_n_effective": 0,
            "control_before_avg": 0.0,
            "control_after_avg": 0.0,
            "control_delta_per_day": 0.0,
            "control_delta_window": 0.0,
            "control_cov_before": float(m["before_days"].mean() / max(window_days, 1)) if len(m) else 0.0,
            "control_cov_after": float(m["after_days"].mean() / max(window_days, 1)) if len(m) else 0.0,
        }

    cb = float(effective["before_avg"].mean())
    ca_ = float(effective["after_avg"].mean())
    dd = ca_ - cb
    dw = dd * float(window_days)

    cov_b = float(effective["before_days"].mean() / max(window_days, 1))
    cov_a = float(effective["after_days"].mean() / max(window_days, 1))

    return {
        "control_n": int(len(control_animals)),
        "control_n_effective": n_eff,
        "control_before_avg": cb,
        "control_after_avg": ca_,
        "control_delta_per_day": float(dd),
        "control_delta_window": float(dw),
        "control_cov_before": cov_b,
        "control_cov_after": cov_a,
    }


def _match_controls_by_baseline_animal(
    *,
    animal_daily: pd.DataFrame,
    candidates: list[str],
    before_start: pd.Timestamp,
    before_end: pd.Timestamp,
    treated_before_avg: float,
    top_k: int,
) -> tuple[list[str], dict[str, Any]]:
    """Pick controls with similar baseline margin (before window).

    Returns: (selected_ids, matching_stats)
    """
    if not candidates or animal_daily.empty or top_k <= 0:
        return candidates, {"matching": False}

    df = animal_daily.copy()
    if "date" not in df.columns:
        return candidates, {"matching": False}

    df["date"] = pd.to_datetime(df.get("date"), errors="coerce").dt.normalize()
    df["margin_rub"] = pd.to_numeric(df.get("margin_rub"), errors="coerce").fillna(0.0)
    df = df[df.get("animal_id").astype(str).isin([str(x) for x in candidates])].copy()
    df = df.dropna(subset=["date"])  # type: ignore
    if df.empty:
        return candidates, {"matching": False}

    b = df[(df["date"] >= before_start) & (df["date"] <= before_end)].copy()
    if b.empty:
        return candidates, {"matching": False}

    bstats = (
        b.groupby("animal_id", dropna=False)
        .agg(before_sum=("margin_rub", "sum"), before_days=("date", "nunique"))
        .reset_index()
    )
    bstats["before_sum"] = pd.to_numeric(bstats.get("before_sum"), errors="coerce").fillna(0.0)
    bstats["before_days"] = pd.to_numeric(bstats.get("before_days"), errors="coerce").fillna(0).astype(int)
    bstats = bstats[bstats["before_days"] > 0].copy()
    if bstats.empty:
        return candidates, {"matching": False}

    bstats["before_avg"] = bstats["before_sum"] / bstats["before_days"].clip(lower=1)
    bstats["dist"] = (bstats["before_avg"] - float(treated_before_avg)).abs()
    bstats = bstats.sort_values(["dist"])  # closest first
    sel = [str(x) for x in bstats.head(int(top_k)).get("animal_id").astype(str).tolist()]

    return sel, {
        "matching": True,
        "matching_metric": "before_margin_avg",
        "matching_top_k": int(top_k),
        "matching_candidates": int(len(candidates)),
        "matching_selected": int(len(sel)),
    }


def _match_controls_by_baseline_group(
    *,
    group_daily: pd.DataFrame,
    object_type: str,
    candidates: list[str],
    before_start: pd.Timestamp,
    before_end: pd.Timestamp,
    treated_before_avg: float,
    top_k: int,
) -> tuple[list[str], dict[str, Any]]:
    """Pick control groups with similar baseline margin (before window)."""
    if not candidates or group_daily.empty or top_k <= 0:
        return candidates, {"matching": False}

    ot = _normalize_object_type(object_type)
    if ot == "pen":
        level = "pen"
        id_col = "pen_id"
    elif ot == "site":
        level = "site"
        id_col = "site_id"
    else:
        return candidates, {"matching": False}

    df = group_daily.copy()
    if "date" not in df.columns:
        return candidates, {"matching": False}

    df["date"] = pd.to_datetime(df.get("date"), errors="coerce").dt.normalize()
    df["margin_rub"] = pd.to_numeric(df.get("margin_rub"), errors="coerce").fillna(0.0)
    df = df[df.get("level").astype(str) == level].copy()
    df = df[df.get(id_col).astype(str).isin([str(x) for x in candidates])].copy()
    df = df.dropna(subset=["date"])  # type: ignore
    if df.empty:
        return candidates, {"matching": False}

    b = df[(df["date"] >= before_start) & (df["date"] <= before_end)].copy()
    if b.empty:
        return candidates, {"matching": False}

    bstats = (
        b.groupby(id_col, dropna=False)
        .agg(before_sum=("margin_rub", "sum"), before_days=("date", "nunique"))
        .reset_index()
    )
    bstats["before_sum"] = pd.to_numeric(bstats.get("before_sum"), errors="coerce").fillna(0.0)
    bstats["before_days"] = pd.to_numeric(bstats.get("before_days"), errors="coerce").fillna(0).astype(int)
    bstats = bstats[bstats["before_days"] > 0].copy()
    if bstats.empty:
        return candidates, {"matching": False}

    bstats["before_avg"] = bstats["before_sum"] / bstats["before_days"].clip(lower=1)
    bstats["dist"] = (bstats["before_avg"] - float(treated_before_avg)).abs()
    bstats = bstats.sort_values(["dist"])  # closest
    sel = [str(x) for x in bstats.head(int(top_k)).get(id_col).astype(str).tolist()]

    return sel, {
        "matching": True,
        "matching_metric": "before_margin_avg",
        "matching_top_k": int(top_k),
        "matching_candidates": int(len(candidates)),
        "matching_selected": int(len(sel)),
    }


def list_roi_runs(*, artifacts_root: Path, data_version: str) -> list[str]:
    root = Path(artifacts_root) / data_version / "roi"
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir()])


def load_roi(*, artifacts_root: Path, data_version: str, roi_run: Optional[str] = None) -> Tuple[str, dict[str, pd.DataFrame], Path]:
    root = Path(artifacts_root) / data_version / "roi"
    if not root.exists():
        raise FileNotFoundError("Нет ROI запусков")

    rid = roi_run
    if not rid:
        runs = list_roi_runs(artifacts_root=artifacts_root, data_version=data_version)
        if not runs:
            raise FileNotFoundError("Нет ROI запусков")
        rid = runs[-1]

    run_dir = root / rid
    if not run_dir.exists():
        raise FileNotFoundError(f"Нет ROI run: {rid}")

    actions = pd.read_csv(run_dir / "roi_actions.csv") if (run_dir / "roi_actions.csv").exists() else pd.DataFrame()
    summary = pd.read_csv(run_dir / "roi_summary.csv") if (run_dir / "roi_summary.csv").exists() else pd.DataFrame()
    quality = pd.read_csv(run_dir / "roi_quality.csv") if (run_dir / "roi_quality.csv").exists() else pd.DataFrame()
    series = pd.read_csv(run_dir / "roi_action_series.csv") if (run_dir / "roi_action_series.csv").exists() else pd.DataFrame()
    comps = pd.read_csv(run_dir / "roi_action_components.csv") if (run_dir / "roi_action_components.csv").exists() else pd.DataFrame()
    return str(rid), {"actions": actions, "summary": summary, "quality": quality, "series": series, "components": comps}, run_dir


def _safe_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out.get(c), errors="coerce")
    return out


def _compute_window_component_stats(
    *,
    series: pd.DataFrame,
    before_start: pd.Timestamp,
    before_end: pd.Timestamp,
    after_start: pd.Timestamp,
    after_end: pd.Timestamp,
    cols: list[str],
) -> dict[str, dict[str, float]]:
    """Return per-component stats (avg per day) for treated series."""
    if series.empty or "date" not in series.columns:
        return {c: {"before_avg": 0.0, "after_avg": 0.0, "delta_per_day": 0.0} for c in cols}

    df = series.copy()
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce").dt.normalize()
    df = df.dropna(subset=["date"])  # type: ignore
    df = _safe_numeric(df, cols)

    b = df[(df["date"] >= before_start) & (df["date"] <= before_end)].copy()
    a = df[(df["date"] >= after_start) & (df["date"] <= after_end)].copy()
    b_days = int(b["date"].nunique()) if not b.empty else 0
    a_days = int(a["date"].nunique()) if not a.empty else 0

    out: dict[str, dict[str, float]] = {}
    for c in cols:
        b_sum = float(pd.to_numeric(b.get(c), errors="coerce").fillna(0.0).sum()) if (not b.empty and c in b.columns) else 0.0
        a_sum = float(pd.to_numeric(a.get(c), errors="coerce").fillna(0.0).sum()) if (not a.empty and c in a.columns) else 0.0
        b_avg = b_sum / max(b_days, 1)
        a_avg = a_sum / max(a_days, 1)
        out[c] = {"before_avg": float(b_avg), "after_avg": float(a_avg), "delta_per_day": float(a_avg - b_avg)}
    return out


def _control_component_avgs_animal(
    *,
    animal_daily: pd.DataFrame,
    control_ids: list[str],
    before_start: pd.Timestamp,
    before_end: pd.Timestamp,
    after_start: pd.Timestamp,
    after_end: pd.Timestamp,
    cols: list[str],
) -> dict[str, dict[str, float]]:
    if animal_daily.empty or not control_ids or "date" not in animal_daily.columns:
        return {c: {"before_avg": 0.0, "after_avg": 0.0, "delta_per_day": 0.0} for c in cols}

    df = animal_daily.copy()
    df = df[df.get("animal_id").astype(str).isin([str(x) for x in control_ids])].copy()
    if df.empty:
        return {c: {"before_avg": 0.0, "after_avg": 0.0, "delta_per_day": 0.0} for c in cols}

    df["date"] = pd.to_datetime(df.get("date"), errors="coerce").dt.normalize()
    df = df.dropna(subset=["date"])  # type: ignore
    df = _safe_numeric(df, cols)

    b = df[(df["date"] >= before_start) & (df["date"] <= before_end)].copy()
    a = df[(df["date"] >= after_start) & (df["date"] <= after_end)].copy()

    if b.empty or a.empty:
        return {c: {"before_avg": 0.0, "after_avg": 0.0, "delta_per_day": 0.0} for c in cols}

    bdays = b.groupby("animal_id", dropna=False).agg(before_days=("date", "nunique")).reset_index()
    adays = a.groupby("animal_id", dropna=False).agg(after_days=("date", "nunique")).reset_index()
    bsum = b.groupby("animal_id", dropna=False)[[c for c in cols if c in b.columns]].sum().reset_index()
    asum = a.groupby("animal_id", dropna=False)[[c for c in cols if c in a.columns]].sum().reset_index()

    m = bdays.merge(adays, on="animal_id", how="outer").merge(bsum, on="animal_id", how="left").merge(asum, on="animal_id", how="left", suffixes=("_b", "_a"))
    m["before_days"] = pd.to_numeric(m.get("before_days"), errors="coerce").fillna(0).astype(int)
    m["after_days"] = pd.to_numeric(m.get("after_days"), errors="coerce").fillna(0).astype(int)
    effective = m[(m["before_days"] > 0) & (m["after_days"] > 0)].copy()
    if effective.empty:
        return {c: {"before_avg": 0.0, "after_avg": 0.0, "delta_per_day": 0.0} for c in cols}

    out: dict[str, dict[str, float]] = {}
    for c in cols:
        # bsum column might be just c (from bsum merge); asum might be c_y? we used suffixes, so assume merged columns are c and c_a? safer:
        bcol = c if c in effective.columns else f"{c}_b"
        acol = f"{c}_a" if f"{c}_a" in effective.columns else c
        bsumv = pd.to_numeric(effective.get(bcol), errors="coerce").fillna(0.0)
        asumv = pd.to_numeric(effective.get(acol), errors="coerce").fillna(0.0)
        bavg = (bsumv / effective["before_days"].clip(lower=1)).mean()
        aavg = (asumv / effective["after_days"].clip(lower=1)).mean()
        out[c] = {"before_avg": float(bavg), "after_avg": float(aavg), "delta_per_day": float(aavg - bavg)}
    return out


def _control_component_avgs_group(
    *,
    group_daily: pd.DataFrame,
    object_type: str,
    control_ids: list[str],
    before_start: pd.Timestamp,
    before_end: pd.Timestamp,
    after_start: pd.Timestamp,
    after_end: pd.Timestamp,
    cols: list[str],
) -> dict[str, dict[str, float]]:
    if group_daily.empty or not control_ids or "date" not in group_daily.columns:
        return {c: {"before_avg": 0.0, "after_avg": 0.0, "delta_per_day": 0.0} for c in cols}

    ot = _normalize_object_type(object_type)
    if ot == "pen":
        level = "pen"
        id_col = "pen_id"
    elif ot == "site":
        level = "site"
        id_col = "site_id"
    else:
        return {c: {"before_avg": 0.0, "after_avg": 0.0, "delta_per_day": 0.0} for c in cols}

    df = group_daily.copy()
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce").dt.normalize()
    df = df.dropna(subset=["date"])  # type: ignore
    df = df[df.get("level").astype(str) == level].copy()
    df = df[df.get(id_col).astype(str).isin([str(x) for x in control_ids])].copy()
    if df.empty:
        return {c: {"before_avg": 0.0, "after_avg": 0.0, "delta_per_day": 0.0} for c in cols}

    df = _safe_numeric(df, cols)
    b = df[(df["date"] >= before_start) & (df["date"] <= before_end)].copy()
    a = df[(df["date"] >= after_start) & (df["date"] <= after_end)].copy()
    if b.empty or a.empty:
        return {c: {"before_avg": 0.0, "after_avg": 0.0, "delta_per_day": 0.0} for c in cols}

    bdays = b.groupby(id_col, dropna=False).agg(before_days=("date", "nunique")).reset_index()
    adays = a.groupby(id_col, dropna=False).agg(after_days=("date", "nunique")).reset_index()
    bsum = b.groupby(id_col, dropna=False)[[c for c in cols if c in b.columns]].sum().reset_index()
    asum = a.groupby(id_col, dropna=False)[[c for c in cols if c in a.columns]].sum().reset_index()
    m = bdays.merge(adays, on=id_col, how="outer").merge(bsum, on=id_col, how="left").merge(asum, on=id_col, how="left", suffixes=("_b", "_a"))
    m["before_days"] = pd.to_numeric(m.get("before_days"), errors="coerce").fillna(0).astype(int)
    m["after_days"] = pd.to_numeric(m.get("after_days"), errors="coerce").fillna(0).astype(int)
    effective = m[(m["before_days"] > 0) & (m["after_days"] > 0)].copy()
    if effective.empty:
        return {c: {"before_avg": 0.0, "after_avg": 0.0, "delta_per_day": 0.0} for c in cols}

    out: dict[str, dict[str, float]] = {}
    for c in cols:
        bcol = c if c in effective.columns else f"{c}_b"
        acol = f"{c}_a" if f"{c}_a" in effective.columns else c
        bsumv = pd.to_numeric(effective.get(bcol), errors="coerce").fillna(0.0)
        asumv = pd.to_numeric(effective.get(acol), errors="coerce").fillna(0.0)
        bavg = (bsumv / effective["before_days"].clip(lower=1)).mean()
        aavg = (asumv / effective["after_days"].clip(lower=1)).mean()
        out[c] = {"before_avg": float(bavg), "after_avg": float(aavg), "delta_per_day": float(aavg - bavg)}
    return out


def run_roi_attribution(
    *,
    artifacts_root: Path,
    data_version: str,
    cfg_path: Path = DEFAULT_CFG_PATH,
    roi_run: Optional[str] = None,
    unit_econ_run: Optional[str] = None,
    economics_run: Optional[str] = None,
    tenant_id: str = "default",
    web_db_path: Optional[Path] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Dict[str, Any]:
    artifacts_root = Path(artifacts_root)
    cfg = _load_cfg(Path(cfg_path))

    roi_cfg = cfg.get("roi") or {}
    window_days = int(roi_cfg.get("window_days") or 14)
    include_action_day = bool(roi_cfg.get("include_action_day") or False)
    min_coverage = float(roi_cfg.get("min_coverage") or 0.6)
    eps_cost = float(roi_cfg.get("eps_cost") or 1.0e-9)
    method_pref = str(roi_cfg.get("method") or "before_after").strip().lower()

    out_cfg = roi_cfg.get("outputs") or {}
    out_series_enabled = bool(out_cfg.get("action_series", False))
    out_components_enabled = bool(out_cfg.get("action_components", False))
    details_max_actions = int(out_cfg.get("details_max_actions") or 0)
    if details_max_actions < 0:
        details_max_actions = 0

    ctrl_cfg = (roi_cfg.get("control") or {})
    ctrl_enabled = bool(ctrl_cfg.get("enabled", True))
    ctrl_scope = str(ctrl_cfg.get("scope") or "pen").strip().lower()
    ctrl_min_n = int(ctrl_cfg.get("min_control_animals") or 3)
    ctrl_min_cov = float(ctrl_cfg.get("min_coverage") or 0.5)
    excl_any = bool(ctrl_cfg.get("exclude_any_action_in_window", True))
    excl_same = bool(ctrl_cfg.get("exclude_same_action_type_in_window", True))

    match_cfg = (ctrl_cfg.get("matching") or {})
    match_enabled = bool(match_cfg.get("enabled", False))
    match_top_k = int(match_cfg.get("top_k") or 10)

    # Group diff-in-diff (pen/site) — separate controls (defaults are safe fallbacks)
    gdid_cfg = (roi_cfg.get("group_did") or {})
    gdid_enabled = bool(gdid_cfg.get("enabled", True))
    gdid_pen_scope = str(gdid_cfg.get("pen_control_scope") or "site").strip().lower()
    gdid_site_scope = str(gdid_cfg.get("site_control_scope") or "farm").strip().lower()
    gdid_min_n = int(gdid_cfg.get("min_control_groups") or 3)
    gdid_min_cov = float(gdid_cfg.get("min_coverage") or 0.5)
    gdid_excl_any = bool(gdid_cfg.get("exclude_any_action_in_window", excl_any))
    gdid_excl_same = bool(gdid_cfg.get("exclude_same_action_type_in_window", excl_same))

    gmatch_cfg = (gdid_cfg.get("matching") or {})
    gmatch_enabled = bool(gmatch_cfg.get("enabled", match_enabled))
    gmatch_top_k = int(gmatch_cfg.get("top_k") or match_top_k)

    accepted = set(
        [str(x).strip().lower() for x in ((cfg.get("sources") or {}).get("decision_log_csv") or {}).get("accepted_values") or []]
    )
    if not accepted:
        accepted = {"accept", "accepted", "yes", "ok", "done", "true", "1"}

    mapping_rules = (cfg.get("cost_mapping") or {}).get("rules") or []

    # Load unit economics
    u_rid, udfs, udir = load_unit_economics(artifacts_root=artifacts_root, data_version=data_version, unit_econ_run=unit_econ_run)
    animal_daily = udfs.get("animal_daily", pd.DataFrame())
    group_daily = udfs.get("group_daily", pd.DataFrame())

    # normalize unit economics data once
    if not animal_daily.empty and "date" in animal_daily.columns:
        animal_daily = animal_daily.copy()
        animal_daily["date"] = pd.to_datetime(animal_daily.get("date"), errors="coerce").dt.normalize()
        animal_daily["margin_rub"] = pd.to_numeric(animal_daily.get("margin_rub"), errors="coerce").fillna(0.0)

    if not group_daily.empty and "date" in group_daily.columns:
        group_daily = group_daily.copy()
        group_daily["date"] = pd.to_datetime(group_daily.get("date"), errors="coerce").dt.normalize()
        group_daily["margin_rub"] = pd.to_numeric(group_daily.get("margin_rub"), errors="coerce").fillna(0.0)

    # economics_run: from unit_economics manifest if not provided
    try:
        uman = json.loads((Path(udir) / "manifest.json").read_text(encoding="utf-8"))
    except Exception:
        uman = {}
    econ_run = str(economics_run or uman.get("economics_run") or "").strip()
    if not econ_run:
        raise ValueError("Не удалось определить economics_run (передайте --economics-run или пересчитайте unit_economics)")

    cost_models = _load_cost_models(artifacts_root=artifacts_root, data_version=data_version, economics_run=econ_run)

    # Load actions
    actions_df = pd.DataFrame()

    if bool(((cfg.get("sources") or {}).get("decision_log_csv") or {}).get("enabled", True)):
        d = _read_decision_log_csv(artifacts_root, data_version)
        if not d.empty:
            d = d[d.get("status_raw").apply(lambda x: _is_accepted(x, accepted))].copy()
            actions_df = pd.concat([actions_df, d], ignore_index=True)

    if web_db_path and bool(((cfg.get("sources") or {}).get("web_db") or {}).get("enabled", True)):
        w = _read_web_db_actions(Path(web_db_path), tenant_id=str(tenant_id or "default"))
        if not w.empty:
            is_dec = w.get("source").astype(str).str.contains("decision_log_v2", na=False)
            if is_dec.any():
                w_dec = w[is_dec].copy()
                w_oth = w[~is_dec].copy()
                w_dec = w_dec[w_dec.get("status_raw").apply(lambda x: _is_accepted(x, accepted))].copy()
                w = pd.concat([w_dec, w_oth], ignore_index=True)
            actions_df = pd.concat([actions_df, w], ignore_index=True)

    if actions_df.empty:
        return {
            "ok": False,
            "reason": "Нет решений/задач для ROI (decision_log пуст и/или web.db не передан)",
            "roi_run": roi_run or "",
        }

    actions_df = actions_df.dropna(subset=["action_date"]).copy()
    actions_df["object_type"] = actions_df.get("object_type").apply(lambda x: _normalize_object_type(str(x) if x is not None else ""))
    actions_df["object_id"] = actions_df.get("object_id").astype(str)
    actions_df["action_type"] = actions_df.get("action_type").astype(str)
    actions_df["action_date"] = pd.to_datetime(actions_df.get("action_date"), errors="coerce").dt.normalize()
    actions_df = actions_df.dropna(subset=["action_date"]).copy()

    # Sort actions so that detail outputs are deterministic (latest first).
    actions_df = actions_df.sort_values(["action_date"], ascending=False).reset_index(drop=True)

    # Filter by date range
    if date_from:
        df_ = _norm_date(date_from)
        if df_ is not None:
            actions_df = actions_df[actions_df["action_date"] >= df_].copy()
    if date_to:
        dt_ = _norm_date(date_to)
        if dt_ is not None:
            actions_df = actions_df[actions_df["action_date"] <= dt_].copy()

    # Compute ROI rows
    out_rows: list[dict[str, Any]] = []
    series_rows: list[dict[str, Any]] = []
    comp_rows: list[dict[str, Any]] = []

    for i, r in actions_df.iterrows():
        obj_type = str(r.get("object_type") or "unknown")
        obj_id = str(r.get("object_id") or "")
        a_type = str(r.get("action_type") or "")
        a_date = r.get("action_date")
        if not obj_id or a_date is None or pd.isna(a_date):
            continue

        ad = pd.to_datetime(a_date).normalize()
        series = _select_series(animal_daily=animal_daily, group_daily=group_daily, object_type=obj_type, object_id=obj_id)
        stats = _compute_before_after(series=series, action_date=ad, window_days=window_days, include_action_day=include_action_day)

        action_id = f"{str(r.get('source'))}:{str(r.get('source_id'))}"

        # cost
        cost, cost_param = _map_action_cost(a_type, mapping_rules=mapping_rules, cost_models=cost_models)

        # coverage treated
        cov_before = stats["before_days"] / float(window_days) if window_days > 0 else 0.0
        cov_after = stats["after_days"] / float(window_days) if window_days > 0 else 0.0

        flags: list[str] = []
        if series is None or series.empty:
            flags.append("MISSING_SERIES")
        if cov_before < min_coverage or cov_after < min_coverage:
            flags.append("LOW_COVERAGE")

        if (cost <= 0.0) and (str(cost_param).strip() == ""):
            flags.append("COST_UNKNOWN")

        # Optional diff-in-diff (animal + group)
        method_used = "before_after"
        control_ids_used: list[str] = []
        ctrl = {
            "control_scope": "",
            "control_n": 0,
            "control_n_effective": 0,
            "control_before_avg": "",
            "control_after_avg": "",
            "control_delta_per_day": "",
            "control_delta_window": "",
            "control_cov_before": "",
            "control_cov_after": "",
            "control_matching": "",
            "control_matching_top_k": "",
            "control_matching_selected": "",
        }

        delta_adj_per_day: Optional[float] = None
        delta_adj_window: Optional[float] = None

        # window bounds for exclusion / control
        before_start, before_end, after_start, after_end = _window_bounds(ad, window_days, include_action_day)

        if (
            method_pref in {"diff_in_diff", "did"}
            and ctrl_enabled
            and _normalize_object_type(obj_type) == "animal"
            and not animal_daily.empty
        ):
            scope_ids = _animal_scope_ids(animal_daily, animal_id=obj_id, action_date=ad)
            cands = _control_candidates(
                animal_daily=animal_daily,
                scope=ctrl_scope,
                scope_ids=scope_ids,
                action_date=ad,
                treated_animal_id=obj_id,
            )
            cands = _filter_controls_by_actions(
                candidates=cands,
                actions_df=actions_df,
                before_start=before_start,
                after_end=after_end,
                action_type=a_type,
                exclude_any=excl_any,
                exclude_same_type=excl_same,
            )

            mstat: dict[str, Any] = {"matching": False}
            if match_enabled:
                cands, mstat = _match_controls_by_baseline_animal(
                    animal_daily=animal_daily,
                    candidates=cands,
                    before_start=before_start,
                    before_end=before_end,
                    treated_before_avg=float(stats.get("before_avg") or 0.0),
                    top_k=int(match_top_k),
                )

            control_ids_used = list(cands)
            cstats = _compute_control_deltas(
                animal_daily=animal_daily,
                control_animals=cands,
                before_start=before_start,
                before_end=before_end,
                after_start=after_start,
                after_end=after_end,
                window_days=window_days,
            )

            ctrl.update(
                {
                    "control_scope": ctrl_scope,
                    "control_n": int(cstats.get("control_n") or 0),
                    "control_n_effective": int(cstats.get("control_n_effective") or 0),
                    "control_before_avg": float(cstats.get("control_before_avg") or 0.0) if int(cstats.get("control_n_effective") or 0) > 0 else "",
                    "control_after_avg": float(cstats.get("control_after_avg") or 0.0) if int(cstats.get("control_n_effective") or 0) > 0 else "",
                    "control_delta_per_day": float(cstats.get("control_delta_per_day") or 0.0) if int(cstats.get("control_n_effective") or 0) > 0 else "",
                    "control_delta_window": float(cstats.get("control_delta_window") or 0.0) if int(cstats.get("control_n_effective") or 0) > 0 else "",
                    "control_cov_before": float(cstats.get("control_cov_before") or 0.0) if int(cstats.get("control_n_effective") or 0) > 0 else "",
                    "control_cov_after": float(cstats.get("control_cov_after") or 0.0) if int(cstats.get("control_n_effective") or 0) > 0 else "",
                    "control_matching": bool(mstat.get("matching")) if mstat else "",
                    "control_matching_top_k": int(mstat.get("matching_top_k") or 0) if mstat and mstat.get("matching") else "",
                    "control_matching_selected": int(mstat.get("matching_selected") or 0) if mstat and mstat.get("matching") else "",
                }
            )

            n_eff = int(cstats.get("control_n_effective") or 0)
            cov_cb = float(cstats.get("control_cov_before") or 0.0)
            cov_ca = float(cstats.get("control_cov_after") or 0.0)

            if n_eff < ctrl_min_n:
                flags.append("NO_CONTROL_GROUP")
            elif cov_cb < ctrl_min_cov or cov_ca < ctrl_min_cov:
                flags.append("LOW_CONTROL_COVERAGE")
            else:
                # DiD
                treated_delta = float(stats.get("delta_per_day") or 0.0)
                control_delta = float(cstats.get("control_delta_per_day") or 0.0)
                delta_adj_per_day = treated_delta - control_delta
                delta_adj_window = float(delta_adj_per_day) * float(window_days)
                method_used = "diff_in_diff"

        # Group DiD (pen/site) — uses unit_economics_group_daily and control groups in broader scope.
        if (
            delta_adj_per_day is None
            and method_pref in {"diff_in_diff", "did"}
            and ctrl_enabled
            and gdid_enabled
            and _normalize_object_type(obj_type) in {"pen", "site"}
            and not group_daily.empty
        ):
            ot = _normalize_object_type(obj_type)
            scope = gdid_pen_scope if ot == "pen" else gdid_site_scope
            scope_ids = _group_scope_ids(group_daily, object_type=ot, object_id=obj_id, action_date=ad)
            cands = _group_control_candidates(
                group_daily=group_daily,
                object_type=ot,
                control_scope=scope,
                scope_ids=scope_ids,
                action_date=ad,
                treated_object_id=obj_id,
            )
            cands = _filter_controls_by_actions_generic(
                candidates=cands,
                actions_df=actions_df,
                before_start=before_start,
                after_end=after_end,
                action_type=a_type,
                object_type=ot,
                exclude_any=gdid_excl_any,
                exclude_same_type=gdid_excl_same,
            )

            gmstat: dict[str, Any] = {"matching": False}
            if gmatch_enabled:
                cands, gmstat = _match_controls_by_baseline_group(
                    group_daily=group_daily,
                    object_type=ot,
                    candidates=cands,
                    before_start=before_start,
                    before_end=before_end,
                    treated_before_avg=float(stats.get("before_avg") or 0.0),
                    top_k=int(gmatch_top_k),
                )

            control_ids_used = list(cands)

            cstats = _compute_control_deltas_group(
                group_daily=group_daily,
                object_type=ot,
                control_ids=cands,
                before_start=before_start,
                before_end=before_end,
                after_start=after_start,
                after_end=after_end,
                window_days=window_days,
            )

            ctrl.update(
                {
                    "control_scope": str(scope),
                    "control_n": int(cstats.get("control_n") or 0),
                    "control_n_effective": int(cstats.get("control_n_effective") or 0),
                    "control_before_avg": float(cstats.get("control_before_avg") or 0.0)
                    if int(cstats.get("control_n_effective") or 0) > 0
                    else "",
                    "control_after_avg": float(cstats.get("control_after_avg") or 0.0)
                    if int(cstats.get("control_n_effective") or 0) > 0
                    else "",
                    "control_delta_per_day": float(cstats.get("control_delta_per_day") or 0.0)
                    if int(cstats.get("control_n_effective") or 0) > 0
                    else "",
                    "control_delta_window": float(cstats.get("control_delta_window") or 0.0)
                    if int(cstats.get("control_n_effective") or 0) > 0
                    else "",
                    "control_cov_before": float(cstats.get("control_cov_before") or 0.0)
                    if int(cstats.get("control_n_effective") or 0) > 0
                    else "",
                    "control_cov_after": float(cstats.get("control_cov_after") or 0.0)
                    if int(cstats.get("control_n_effective") or 0) > 0
                    else "",
                    "control_matching": bool(gmstat.get("matching")) if gmstat else "",
                    "control_matching_top_k": int(gmstat.get("matching_top_k") or 0) if gmstat and gmstat.get("matching") else "",
                    "control_matching_selected": int(gmstat.get("matching_selected") or 0) if gmstat and gmstat.get("matching") else "",
                }
            )

            n_eff = int(cstats.get("control_n_effective") or 0)
            cov_cb = float(cstats.get("control_cov_before") or 0.0)
            cov_ca = float(cstats.get("control_cov_after") or 0.0)

            if n_eff < gdid_min_n:
                flags.append("NO_CONTROL_GROUP")
            elif cov_cb < gdid_min_cov or cov_ca < gdid_min_cov:
                flags.append("LOW_CONTROL_COVERAGE")
            else:
                treated_delta = float(stats.get("delta_per_day") or 0.0)
                control_delta = float(cstats.get("control_delta_per_day") or 0.0)
                delta_adj_per_day = treated_delta - control_delta
                delta_adj_window = float(delta_adj_per_day) * float(window_days)
                method_used = "diff_in_diff"

        # used effect
        delta_used_per_day = float(delta_adj_per_day) if delta_adj_per_day is not None else float(stats.get("delta_per_day") or 0.0)
        delta_used_window = float(delta_adj_window) if delta_adj_window is not None else float(stats.get("delta_window") or 0.0)

        # ROI
        roi_ratio_raw: Optional[float] = None
        roi_ratio_used: Optional[float] = None
        if cost > 0:
            roi_ratio_raw = (float(stats.get("delta_window") or 0.0) - cost) / max(cost, eps_cost)
            roi_ratio_used = (float(delta_used_window) - cost) / max(cost, eps_cost)

        quality_flag = "OK" if not flags else "|".join(sorted(set(flags)))
        quality_reasons = "|".join([QUALITY_REASON_MAP.get(f, f) for f in sorted(set(flags))]) if flags else ""

        details_available = False
        do_details = details_max_actions > 0 and (i < details_max_actions) and (out_series_enabled or out_components_enabled)
        if do_details and series is not None and not series.empty and "date" in series.columns:
            # --- detail: per-day series (treated vs control mean) ---
            try:
                s = series.copy()
                s["date"] = pd.to_datetime(s.get("date"), errors="coerce").dt.normalize()
                s = s.dropna(subset=["date"])  # type: ignore

                cols_series = [c for c in DETAIL_SERIES_COLS if c in s.columns]
                if cols_series:
                    s = _safe_numeric(s, cols_series)
                rng = pd.date_range(before_start, after_end, freq="D")
                frame = pd.DataFrame({"date": rng})
                t = s[(s["date"] >= before_start) & (s["date"] <= after_end)].copy()
                t = t[["date"] + cols_series].copy() if cols_series else t[["date"]].copy()
                for c in cols_series:
                    t.rename(columns={c: f"treated_{c}"}, inplace=True)
                frame = frame.merge(t, on="date", how="left")

                if control_ids_used and method_used == "diff_in_diff":
                    ot = _normalize_object_type(obj_type)
                    if ot == "animal":
                        cdf = animal_daily.copy()
                        cdf = cdf[cdf.get("animal_id").astype(str).isin([str(x) for x in control_ids_used])].copy()
                        cdf = cdf[(cdf["date"] >= before_start) & (cdf["date"] <= after_end)].copy()
                        if not cdf.empty and cols_series:
                            cdf = _safe_numeric(cdf, cols_series)
                            cm = cdf.groupby("date", dropna=False)[cols_series].mean().reset_index()
                            for c in cols_series:
                                cm.rename(columns={c: f"control_{c}"}, inplace=True)
                            frame = frame.merge(cm, on="date", how="left")
                    elif ot in {"pen", "site"}:
                        level = "pen" if ot == "pen" else "site"
                        id_col = "pen_id" if ot == "pen" else "site_id"
                        cdf = group_daily.copy()
                        cdf = cdf[cdf.get("level").astype(str) == level].copy()
                        cdf = cdf[cdf.get(id_col).astype(str).isin([str(x) for x in control_ids_used])].copy()
                        cdf = cdf[(cdf["date"] >= before_start) & (cdf["date"] <= after_end)].copy()
                        if not cdf.empty and cols_series:
                            cdf = _safe_numeric(cdf, cols_series)
                            cm = cdf.groupby("date", dropna=False)[cols_series].mean().reset_index()
                            for c in cols_series:
                                cm.rename(columns={c: f"control_{c}"}, inplace=True)
                            frame = frame.merge(cm, on="date", how="left")

                frame["action_id"] = action_id
                frame["object_type"] = _normalize_object_type(obj_type)
                frame["object_id"] = obj_id
                frame["action_type"] = a_type
                frame["action_date"] = pd.to_datetime(ad).date().isoformat()
                frame["method"] = method_used
                frame["quality_flag"] = quality_flag
                frame["relative_day"] = (frame["date"] - pd.to_datetime(ad)).dt.days
                frame["window_part"] = frame["relative_day"].apply(lambda x: "before" if x < 0 else ("after" if x > 0 else "action"))
                frame["date"] = frame["date"].dt.date.astype(str)

                if out_series_enabled:
                    series_rows.extend(frame.to_dict(orient="records"))
                    details_available = True
            except Exception:
                pass

            # --- detail: component breakdown (treated vs control) ---
            if out_components_enabled:
                try:
                    cols_comp = [c for c in DETAIL_COMPONENT_COLS if c in series.columns]
                    treated = _compute_window_component_stats(
                        series=series,
                        before_start=before_start,
                        before_end=before_end,
                        after_start=after_start,
                        after_end=after_end,
                        cols=cols_comp,
                    )

                    control = {c: {"before_avg": 0.0, "after_avg": 0.0, "delta_per_day": 0.0} for c in cols_comp}
                    if control_ids_used and method_used == "diff_in_diff":
                        ot = _normalize_object_type(obj_type)
                        if ot == "animal":
                            control = _control_component_avgs_animal(
                                animal_daily=animal_daily,
                                control_ids=control_ids_used,
                                before_start=before_start,
                                before_end=before_end,
                                after_start=after_start,
                                after_end=after_end,
                                cols=cols_comp,
                            )
                        elif ot in {"pen", "site"}:
                            control = _control_component_avgs_group(
                                group_daily=group_daily,
                                object_type=ot,
                                control_ids=control_ids_used,
                                before_start=before_start,
                                before_end=before_end,
                                after_start=after_start,
                                after_end=after_end,
                                cols=cols_comp,
                            )

                    for c in cols_comp:
                        t0 = float(treated.get(c, {}).get("before_avg") or 0.0)
                        t1 = float(treated.get(c, {}).get("after_avg") or 0.0)
                        td = float(treated.get(c, {}).get("delta_per_day") or 0.0)
                        c0 = float(control.get(c, {}).get("before_avg") or 0.0)
                        c1 = float(control.get(c, {}).get("after_avg") or 0.0)
                        cd = float(control.get(c, {}).get("delta_per_day") or 0.0)
                        did = td - cd
                        used = did if method_used == "diff_in_diff" else td
                        comp_rows.append(
                            {
                                "action_id": action_id,
                                "object_type": _normalize_object_type(obj_type),
                                "object_id": obj_id,
                                "action_type": a_type,
                                "action_date": pd.to_datetime(ad).date().isoformat(),
                                "window_days": int(window_days),
                                "method": method_used,
                                "component": c,
                                "treated_before_avg": t0,
                                "treated_after_avg": t1,
                                "control_before_avg": c0 if method_used == "diff_in_diff" else "",
                                "control_after_avg": c1 if method_used == "diff_in_diff" else "",
                                "delta_per_day_raw": td,
                                "delta_per_day_adj": did if method_used == "diff_in_diff" else "",
                                "delta_per_day_used": used,
                                "delta_window_used": float(used) * float(window_days),
                                "quality_flag": quality_flag,
                            }
                        )
                    details_available = True
                except Exception:
                    pass

        out_rows.append(
            {
                "action_id": action_id,
                "source": str(r.get("source")),
                "source_id": str(r.get("source_id")),
                "object_type": _normalize_object_type(obj_type),
                "object_id": obj_id,
                "action_type": a_type,
                "action_date": pd.to_datetime(ad).date().isoformat(),
                "window_days": int(window_days),
                "method": method_used,
                "before_days": int(stats["before_days"]),
                "after_days": int(stats["after_days"]),
                "before_margin_sum": float(stats["before_sum"]),
                "after_margin_sum": float(stats["after_sum"]),
                "before_margin_avg": float(stats["before_avg"]),
                "after_margin_avg": float(stats["after_avg"]),
                "delta_margin_per_day": float(stats["delta_per_day"]),
                "delta_margin_window": float(stats["delta_window"]),
                "delta_margin_per_day_adj": float(delta_adj_per_day) if delta_adj_per_day is not None else "",
                "delta_margin_window_adj": float(delta_adj_window) if delta_adj_window is not None else "",
                "delta_margin_per_day_used": float(delta_used_per_day),
                "delta_margin_window_used": float(delta_used_window),
                "cost_rub": float(cost),
                "cost_param": str(cost_param),
                "roi_ratio": float(roi_ratio_raw) if roi_ratio_raw is not None else "",
                "roi_ratio_used": float(roi_ratio_used) if roi_ratio_used is not None else "",
                "quality_flag": quality_flag,
                "quality_reasons": quality_reasons,
                "details_available": bool(details_available),
                "coverage_before": float(cov_before),
                "coverage_after": float(cov_after),
                **ctrl,
                "comment": str(r.get("comment") or ""),
                "reason": str(r.get("reason") or ""),
                "data_version": str(r.get("data_version") or data_version),
                "qc_run": str(r.get("qc_run") or ""),
                "model_version": str(r.get("model_version") or ""),
                "scoring_run": str(r.get("scoring_run") or ""),
                "report_version": str(r.get("report_version") or ""),
                "unit_econ_run": str(u_rid),
                "economics_run": str(econ_run),
            }
        )

    roi_actions = pd.DataFrame(out_rows)
    if roi_actions.empty:
        return {"ok": False, "reason": "Не удалось сопоставить действия с витриной unit_economics", "roi_run": roi_run or ""}

    # summary by month + action_type (+ method)
    roi_actions["action_month"] = pd.to_datetime(roi_actions["action_date"], errors="coerce").dt.to_period("M").astype(str)
    roi_actions["cost_rub"] = pd.to_numeric(roi_actions["cost_rub"], errors="coerce").fillna(0.0)
    for c in ["delta_margin_window", "delta_margin_window_used", "delta_margin_window_adj"]:
        if c in roi_actions.columns:
            roi_actions[c] = pd.to_numeric(roi_actions[c], errors="coerce")

    grp_cols = ["action_month", "object_type", "action_type", "method"]
    grp = roi_actions.groupby(grp_cols, dropna=False)

    summary = (
        grp.agg(
            n_actions=("action_id", "count"),
            delta_margin_window_sum=("delta_margin_window", "sum"),
            delta_margin_window_used_sum=("delta_margin_window_used", "sum"),
            cost_sum=("cost_rub", "sum"),
            delta_margin_window_avg=("delta_margin_window", "mean"),
            delta_margin_window_used_avg=("delta_margin_window_used", "mean"),
        )
        .reset_index()
    )

    # weighted ROI computed from sums (stable, no groupby.apply)
    summary["roi_weighted"] = pd.NA
    summary["roi_weighted_used"] = pd.NA
    c = pd.to_numeric(summary.get("cost_sum"), errors="coerce")
    d_raw = pd.to_numeric(summary.get("delta_margin_window_sum"), errors="coerce")
    d_used = pd.to_numeric(summary.get("delta_margin_window_used_sum"), errors="coerce")
    mask = c.fillna(0.0) > 0
    summary.loc[mask, "roi_weighted"] = (d_raw[mask].fillna(0.0) - c[mask]) / c[mask].clip(lower=eps_cost)
    summary.loc[mask, "roi_weighted_used"] = (d_used[mask].fillna(0.0) - c[mask]) / c[mask].clip(lower=eps_cost)

    # Quality breakdown (reproducible, for UI)
    q = roi_actions.copy()
    q["cost_rub"] = pd.to_numeric(q.get("cost_rub"), errors="coerce").fillna(0.0)
    q["delta_margin_window_used"] = pd.to_numeric(q.get("delta_margin_window_used"), errors="coerce").fillna(0.0)
    q["delta_margin_window"] = pd.to_numeric(q.get("delta_margin_window"), errors="coerce").fillna(0.0)
    q["n"] = 1
    qg = (
        q.groupby(["quality_flag", "method", "object_type"], dropna=False)
        .agg(
            n_actions=("n", "sum"),
            effect_used_sum=("delta_margin_window_used", "sum"),
            effect_raw_sum=("delta_margin_window", "sum"),
            cost_sum=("cost_rub", "sum"),
            avg_cov_before=("coverage_before", "mean"),
            avg_cov_after=("coverage_after", "mean"),
            avg_ctrl_eff=("control_n_effective", "mean"),
        )
        .reset_index()
    )
    total_actions = float(qg["n_actions"].sum()) if not qg.empty else 0.0
    if total_actions > 0:
        qg["share"] = qg["n_actions"] / total_actions
    else:
        qg["share"] = 0.0

    # Write artifacts
    rid = roi_run or generate_run_id(prefix="roi")
    out_dir = artifacts_root / data_version / "roi" / rid
    out_dir.mkdir(parents=True, exist_ok=True)

    roi_actions = roi_actions.sort_values(["action_date"], ascending=False)
    roi_actions.to_csv(out_dir / "roi_actions.csv", index=False)

    summary = summary.sort_values(["action_month", "object_type", "action_type", "method"], ascending=[False, True, True, True])
    summary.to_csv(out_dir / "roi_summary.csv", index=False)

    manifest = {
        "schema": "genomeai.roi_attribution.manifest.v2",
        "created_at_utc": _utc_ts(),
        "data_version": data_version,
        "tenant_id": tenant_id,
        "roi_run": rid,
        "unit_econ_run": u_rid,
        "economics_run": econ_run,
        "cfg": str(Path(cfg_path)),
        "roi": {
            "window_days": window_days,
            "include_action_day": include_action_day,
            "min_coverage": min_coverage,
            "method": method_pref,
            "control": {
                "enabled": ctrl_enabled,
                "scope": ctrl_scope,
                "min_control_animals": ctrl_min_n,
                "min_coverage": ctrl_min_cov,
                "exclude_any_action_in_window": excl_any,
                "exclude_same_action_type_in_window": excl_same,
                "matching": {"enabled": match_enabled, "top_k": match_top_k},
            },
            "group_did": {
                "enabled": gdid_enabled,
                "pen_control_scope": gdid_pen_scope,
                "site_control_scope": gdid_site_scope,
                "min_control_groups": gdid_min_n,
                "min_coverage": gdid_min_cov,
                "exclude_any_action_in_window": gdid_excl_any,
                "exclude_same_action_type_in_window": gdid_excl_same,
                "matching": {"enabled": gmatch_enabled, "top_k": gmatch_top_k},
            },
            "outputs": {
                "action_series": out_series_enabled,
                "action_components": out_components_enabled,
                "details_max_actions": details_max_actions,
            },
        },
        "sources": {
            "decision_log_csv": str((Path(artifacts_root) / data_version / "decisions" / "decision_log.csv").resolve()),
            "web_db": str(Path(web_db_path).resolve()) if web_db_path else "",
        },
        "cost_models": cost_models,
        "limitations": cfg.get("limitations") or [],
    }
    write_json(out_dir / "manifest.json", manifest)

    # Target run layout copy
    run_root = ensure_run_dir(artifacts_root=artifacts_root, data_version=data_version, run_id=rid)
    sub = run_root / "roi"
    sub.mkdir(parents=True, exist_ok=True)
    qg.to_csv(out_dir / "roi_quality.csv", index=False)

    # Optional detail artifacts (series + components)
    if series_rows:
        pd.DataFrame(series_rows).to_csv(out_dir / "roi_action_series.csv", index=False)
    if comp_rows:
        pd.DataFrame(comp_rows).to_csv(out_dir / "roi_action_components.csv", index=False)

    for fn in [
        "roi_actions.csv",
        "roi_summary.csv",
        "roi_quality.csv",
        "roi_action_series.csv",
        "roi_action_components.csv",
        "manifest.json",
    ]:
        p = out_dir / fn
        if p.exists():
            (sub / fn).write_bytes(p.read_bytes())

    out_map: dict[str, str] = {
        "roi_actions": "roi/roi_actions.csv",
        "roi_summary": "roi/roi_summary.csv",
        "roi_quality": "roi/roi_quality.csv",
        "roi_manifest": "roi/manifest.json",
    }
    if (sub / "roi_action_series.csv").exists():
        out_map["roi_action_series"] = "roi/roi_action_series.csv"
    if (sub / "roi_action_components.csv").exists():
        out_map["roi_action_components"] = "roi/roi_action_components.csv"

    write_run_manifest(
        run_root=run_root,
        manifest={
            "schema": "genomeai.run_manifest.v1",
            "run_id": rid,
            "data_version": data_version,
            "step": "roi_attribution",
            "created_at_utc": _utc_ts(),
            "inputs": {"unit_econ_run": u_rid, "economics_run": econ_run},
            "outputs": out_map,
        },
    )
    write_checksums(run_root=run_root, include_subdirs=["roi"])

    # metadata latest pointer (best-effort)
    meta_dir = artifacts_root / data_version / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    meta_path = meta_dir / "roi_manifest.json"
    try:
        mobj = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
    except Exception:
        mobj = None
    if not mobj:
        mobj = {"schema": "genomeai.roi_runs_manifest.v1", "data_version": data_version, "runs": {}, "latest": None}
    mobj["runs"][rid] = {"created_at_utc": manifest["created_at_utc"], "unit_econ_run": u_rid, "economics_run": econ_run}
    mobj["latest"] = rid
    write_json(meta_path, mobj)

    return {"ok": True, "roi_run": rid, "unit_econ_run": u_rid, "economics_run": econ_run, "rows": int(len(roi_actions))}

from __future__ import annotations

"""T5-01: Reproduction KPI + worklists (rule-based).

Offline-core only:
 - loads canonical dm_* tables
 - computes farm KPIs (days open, conception rate, pregnancy rate, service period)
 - generates three worklists: insemination / diagnostics / repeat

No diagnoses are produced: only *risk/actions* and scheduling hints.
"""

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import yaml

from .versioning import write_json


def _utc_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_repro_run_id() -> str:
    rnd = hashlib.sha256(str(time.time()).encode("utf-8")).hexdigest()[:6]
    return time.strftime(f"repro_%Y%m%d_%H%M%S_{rnd}", time.gmtime())


def _parse_date(x: Any) -> Optional[date]:
    if x is None:
        return None
    if isinstance(x, float) and pd.isna(x):
        return None
    if isinstance(x, date) and not isinstance(x, datetime):
        return x
    try:
        return pd.to_datetime(x, errors="coerce").date()
    except Exception:
        return None


def _as_str(x: Any) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and pd.isna(x):
        return ""
    return str(x)


def _load_csv(dir_: Path, name: str) -> pd.DataFrame:
    p = dir_ / name
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p)


def _ensure_cols(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    for c in cols:
        if c not in df.columns:
            df[c] = pd.NA
    return df


def _match_any(text: str, patterns: List[str]) -> bool:
    t = (text or "").lower()
    return any(p.lower() in t for p in patterns)


def _to_bool_result(result: Any, pregnant_vals: List[str], not_pregnant_vals: List[str]) -> Optional[bool]:
    s = _as_str(result).strip().lower()
    if not s:
        return None
    if s in [v.lower() for v in pregnant_vals]:
        return True
    if s in [v.lower() for v in not_pregnant_vals]:
        return False
    # tolerate common synonyms
    if s in {"preg", "p", "pos"}:
        return True
    if s in {"neg", "n", "open"}:
        return False
    return None


def _priority_from_bins(value: int, bins: List[dict], *, min_key: str, pr_key: str) -> int:
    # bins are sorted by min desc in config; but tolerate any order
    best = 5
    for b in bins:
        try:
            mn = int(b.get(min_key, 0))
            pr = int(b.get(pr_key, 5))
        except Exception:
            continue
        if value >= mn:
            best = min(best, pr)
    return int(best)


@dataclass(frozen=True)
class ReproKpiRow:
    tenant_id: str
    farm_id: str
    asof_date: str
    kpi_id: str
    value: float
    unit: str
    period_days: int
    sources_json: str
    notes: str = ""


def compute_repro(
    *,
    input_dir: Path,
    asof_date: date,
    cfg: dict,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (kpis_farm, worklists, cows_snapshot)."""
    # Load
    animals = _load_csv(input_dir, "dm_animals.csv")
    lact = _load_csv(input_dir, "dm_lactations.csv")
    repro = _load_csv(input_dir, "dm_repro_events.csv")

    animals = _ensure_cols(animals, ["tenant_id", "animal_id", "farm_id", "status"])
    lact = _ensure_cols(lact, ["tenant_id", "animal_id", "lactation_id", "lactation_no", "calving_date", "farm_id"])
    repro = _ensure_cols(repro, ["tenant_id", "animal_id", "event_date", "event_type", "result", "farm_id"])

    if not lact.empty:
        lact["calving_date_d"] = pd.to_datetime(lact["calving_date"], errors="coerce").dt.date
    if not repro.empty:
        repro["event_date_d"] = pd.to_datetime(repro["event_date"], errors="coerce").dt.date

    # Derive farms
    farms: List[Tuple[str, str]] = []
    if not animals.empty and "farm_id" in animals.columns:
        farms = animals[["tenant_id", "farm_id"]].dropna().drop_duplicates().values.tolist()
    elif not lact.empty and "farm_id" in lact.columns:
        farms = lact[["tenant_id", "farm_id"]].dropna().drop_duplicates().values.tolist()
    else:
        farms = [["default", "UNKNOWN"]]

    # Config
    defaults = (cfg or {}).get("defaults", {}) or {}
    parsing = (cfg or {}).get("parsing", {}) or {}
    wcfg = (cfg or {}).get("worklists", {}) or {}

    vwp = int(defaults.get("voluntary_waiting_period_days", 50))
    preg_due = int(defaults.get("preg_check_due_days", 32))
    repeat_neg = int(defaults.get("repeat_due_days_if_negative", 1))
    repeat_no_check = int(defaults.get("repeat_due_days_no_check", 60))
    lb_conc = int(defaults.get("lookback_conception_days", 60))
    lb_pr = int(defaults.get("lookback_pregnancy_rate_days", 21))

    insemin_pat = list(parsing.get("insemination_event_type_contains") or ["insemin", "service", "ai"])
    preg_pat = list(parsing.get("pregcheck_event_type_contains") or ["preg", "diagnosis", "pd"])
    preg_vals = list(parsing.get("pregnant_result_values") or ["pregnant", "positive", "yes"])
    not_preg_vals = list(parsing.get("not_pregnant_result_values") or ["open", "negative", "no"])

    pr_insem_bins = list(wcfg.get("insemination_priority_by_dim") or [])
    pr_diag_bins = list(wcfg.get("diagnostics_priority_by_days_since_service") or [])
    pr_rep_bins = list(wcfg.get("repeat_priority_by_days_since_service") or [])

    # Pre-sort events
    if not repro.empty:
        repro = repro[repro["event_date_d"].notna()].copy()
    if not lact.empty:
        lact = lact[lact["calving_date_d"].notna()].copy()

    # Build per-cow snapshot
    cows_rows: List[dict[str, Any]] = []
    wl_rows: List[dict[str, Any]] = []
    kpi_rows: List[ReproKpiRow] = []

    def add_kpi(tenant_id: str, farm_id: str, kpi_id: str, value: Any, unit: str, period_days: int, sources: List[str], notes: str = ""):
        if value is None:
            return
        try:
            fv = float(value)
        except Exception:
            return
        if pd.isna(fv):
            return
        kpi_rows.append(
            ReproKpiRow(
                tenant_id=tenant_id,
                farm_id=farm_id,
                asof_date=asof_date.isoformat(),
                kpi_id=kpi_id,
                value=float(fv),
                unit=unit,
                period_days=int(period_days),
                sources_json=json.dumps(sources, ensure_ascii=False),
                notes=notes,
            )
        )

    # Helper per farm
    for tenant_id, farm_id in farms:
        # farm cows
        a = animals
        if not a.empty:
            a = a[(a["tenant_id"] == tenant_id) & (a["farm_id"] == farm_id)].copy()
        else:
            a = pd.DataFrame(columns=["tenant_id", "animal_id", "farm_id", "status"])

        # lactations: latest calving per cow
        lf = lact
        if not lf.empty:
            lf = lf[(lf["tenant_id"] == tenant_id) & (lf.get("farm_id") == farm_id)].copy() if "farm_id" in lf.columns else lf[lf["tenant_id"] == tenant_id].copy()
            lf = lf[lf["calving_date_d"] <= asof_date].copy()
        # repro events
        rf = repro
        if not rf.empty:
            rf = rf[(rf["tenant_id"] == tenant_id) & (rf.get("farm_id") == farm_id)].copy() if "farm_id" in rf.columns else rf[rf["tenant_id"] == tenant_id].copy()
            rf = rf[rf["event_date_d"] <= asof_date].copy()

        # Determine cow list
        cow_ids: List[str] = []
        if not a.empty:
            cow_ids = sorted(a["animal_id"].dropna().astype(str).unique().tolist())
        elif not lf.empty:
            cow_ids = sorted(lf["animal_id"].dropna().astype(str).unique().tolist())
        elif not rf.empty:
            cow_ids = sorted(rf["animal_id"].dropna().astype(str).unique().tolist())
        else:
            cow_ids = []

        # Prepare for KPI aggregations
        open_days: List[int] = []
        preg_days: List[int] = []
        sp_days: List[int] = []

        # conception events mapped to service date
        conception_service_dates: List[date] = []
        services_in_lb: int = 0
        successful_services_in_lb: int = 0

        # For pregnancy rate (simple 21d)
        pregnancies_in_lb_pr: int = 0
        eligible_cows_pr: int = 0

        for animal_id in cow_ids:
            # latest calving
            cow_lacts = lf[lf["animal_id"].astype(str) == str(animal_id)] if not lf.empty else pd.DataFrame()
            if cow_lacts.empty:
                calving = None
                lactation_id = None
                lactation_no = None
            else:
                cow_lacts = cow_lacts.sort_values("calving_date_d")
                last = cow_lacts.iloc[-1]
                calving = last.get("calving_date_d")
                lactation_id = last.get("lactation_id")
                lactation_no = last.get("lactation_no")

            if not calving or pd.isna(calving):
                # can't compute most repro KPIs without calving
                cows_rows.append(
                    {
                        "tenant_id": tenant_id,
                        "farm_id": farm_id,
                        "animal_id": animal_id,
                        "asof_date": asof_date.isoformat(),
                        "calving_date": None,
                        "days_in_milk": None,
                        "lactation_id": lactation_id,
                        "lactation_no": lactation_no,
                        "pregnant": None,
                        "first_service_date": None,
                        "last_service_date": None,
                        "service_count": 0,
                        "last_pregcheck_date": None,
                        "last_pregcheck_result": None,
                        "conception_service_date": None,
                        "days_open": None,
                        "service_period_days": None,
                    }
                )
                continue

            dim = (asof_date - calving).days

            # events after calving
            cow_events = rf[rf["animal_id"].astype(str) == str(animal_id)] if not rf.empty else pd.DataFrame()
            if not cow_events.empty:
                cow_events = cow_events[cow_events["event_date_d"] >= calving].copy()
                cow_events = cow_events.sort_values("event_date_d")

            # services
            if not cow_events.empty:
                is_service = cow_events["event_type"].astype(str).apply(lambda s: _match_any(s, insemin_pat))
                services = cow_events[is_service].copy()
            else:
                services = pd.DataFrame()
            service_dates = services["event_date_d"].tolist() if not services.empty else []
            first_service = service_dates[0] if service_dates else None
            last_service = service_dates[-1] if service_dates else None
            service_count = int(len(service_dates))

            # pregnancy checks
            if not cow_events.empty:
                is_preg = cow_events["event_type"].astype(str).apply(lambda s: _match_any(s, preg_pat))
                pregchecks = cow_events[is_preg].copy()
            else:
                pregchecks = pd.DataFrame()

            last_preg_dt: Optional[date] = None
            last_preg_res: Optional[bool] = None
            conception_service: Optional[date] = None
            pregnant: Optional[bool] = None

            if not pregchecks.empty:
                pregchecks = pregchecks.sort_values("event_date_d")
                # last pregcheck
                last_row = pregchecks.iloc[-1]
                last_preg_dt = last_row.get("event_date_d")
                last_preg_res = _to_bool_result(last_row.get("result"), preg_vals, not_preg_vals)

                # find first positive pregcheck after last service
                # Strategy: consider positive pregchecks and map each to most recent service before it.
                pos = []
                for _, r in pregchecks.iterrows():
                    res = _to_bool_result(r.get("result"), preg_vals, not_preg_vals)
                    if res is True:
                        pos.append((r.get("event_date_d"), res))
                if pos and service_dates:
                    # map earliest positive check to last service before it
                    pos_dt = sorted([d for d, _ in pos])[0]
                    cand = [sd for sd in service_dates if sd and sd <= pos_dt]
                    if cand:
                        conception_service = max(cand)
                        pregnant = True

                if pregnant is None and last_preg_res is not None:
                    pregnant = bool(last_preg_res)

            if pregnant is None:
                # no pregcheck info: assume open if not yet confirmed pregnant
                pregnant = False

            # days open and service period
            if pregnant and conception_service:
                days_open = (conception_service - calving).days
            else:
                days_open = dim
            service_period = (first_service - calving).days if first_service else None

            # accumulate
            if dim >= vwp:
                if pregnant:
                    preg_days.append(int(days_open))
                else:
                    open_days.append(int(days_open))

                if not pregnant:
                    eligible_cows_pr += 1

            if service_period is not None and dim >= 0:
                sp_days.append(int(service_period))

            # conception rate lookback
            start_lb = asof_date - timedelta(days=lb_conc - 1)
            if last_service is not None and last_service >= start_lb:
                # count all services in lookback
                services_in_lb += int(sum(1 for sd in service_dates if sd and sd >= start_lb))
            # successful services in lookback: conception_service in window
            if conception_service and conception_service >= start_lb:
                successful_services_in_lb += 1
                conception_service_dates.append(conception_service)

            # pregnancy rate lookback (simple): pregnancies whose conception service date in last lb_pr days
            start_pr = asof_date - timedelta(days=lb_pr - 1)
            if conception_service and conception_service >= start_pr:
                pregnancies_in_lb_pr += 1

            # Worklists
            due_reason: Optional[str] = None
            due_action: Optional[str] = None
            wl_type: Optional[str] = None
            priority: Optional[int] = None
            due_at: Optional[date] = None
            details: Dict[str, Any] = {
                "dim": int(dim),
                "vwp_days": int(vwp),
                "preg_check_due_days": int(preg_due),
            }

            if not pregnant and dim >= vwp:
                if not last_service:
                    wl_type = "insemination"
                    due_reason = "Корове требуется первое осеменение (прошёл VWP, услуг нет)"
                    due_action = "Осеменение (по охоте/протоколу)"
                    priority = _priority_from_bins(dim, pr_insem_bins, min_key="min_dim", pr_key="priority")
                    due_at = asof_date
                else:
                    # Diagnostics if service was done and it's time to check pregnancy
                    days_since_service = (asof_date - last_service).days
                    details["days_since_last_service"] = int(days_since_service)

                    # Is there any pregcheck after last service?
                    has_check_after_service = False
                    if not pregchecks.empty:
                        has_check_after_service = bool((pregchecks["event_date_d"] >= last_service).any())

                    # Negative check => repeat
                    if last_preg_res is False and last_preg_dt and last_service and last_preg_dt >= last_service:
                        wl_type = "repeat"
                        due_reason = "Отрицательная диагностика стельности после последнего осеменения"
                        due_action = "Повторное осеменение (по протоколу)"
                        priority = 1
                        due_at = last_preg_dt + timedelta(days=repeat_neg)
                    elif (not has_check_after_service) and (days_since_service >= preg_due):
                        wl_type = "diagnostics"
                        due_reason = "Диагностика стельности просрочена (нет результата после осеменения)"
                        due_action = "Диагностика стельности (УЗИ/ректально)"
                        priority = _priority_from_bins(days_since_service, pr_diag_bins, min_key="min_days", pr_key="priority")
                        due_at = asof_date
                    elif (not has_check_after_service) and (days_since_service >= repeat_no_check):
                        wl_type = "repeat"
                        due_reason = "Нет диагностики стельности слишком долго после осеменения"
                        due_action = "Проверка + повтор по результату"
                        priority = _priority_from_bins(days_since_service, pr_rep_bins, min_key="min_days", pr_key="priority")
                        due_at = asof_date

            if wl_type:
                wl_rows.append(
                    {
                        "tenant_id": tenant_id,
                        "farm_id": farm_id,
                        "asof_date": asof_date.isoformat(),
                        "worklist_type": wl_type,
                        "priority": int(priority or 5),
                        "animal_id": animal_id,
                        "lactation_id": _as_str(lactation_id),
                        "lactation_no": lactation_no,
                        "calving_date": calving.isoformat(),
                        "days_in_milk": int(dim),
                        "first_service_date": first_service.isoformat() if first_service else "",
                        "last_service_date": last_service.isoformat() if last_service else "",
                        "last_pregcheck_date": last_preg_dt.isoformat() if last_preg_dt else "",
                        "last_pregcheck_result": ("pregnant" if last_preg_res is True else "not_pregnant" if last_preg_res is False else ""),
                        "reason": due_reason or "",
                        "next_action": due_action or "",
                        "due_date": due_at.isoformat() if isinstance(due_at, date) else "",
                        "details_json": json.dumps(details, ensure_ascii=False),
                    }
                )

            cows_rows.append(
                {
                    "tenant_id": tenant_id,
                    "farm_id": farm_id,
                    "animal_id": animal_id,
                    "asof_date": asof_date.isoformat(),
                    "calving_date": calving.isoformat() if isinstance(calving, date) else None,
                    "days_in_milk": int(dim),
                    "lactation_id": _as_str(lactation_id),
                    "lactation_no": lactation_no,
                    "pregnant": bool(pregnant) if pregnant is not None else None,
                    "first_service_date": first_service.isoformat() if first_service else None,
                    "last_service_date": last_service.isoformat() if last_service else None,
                    "service_count": int(service_count),
                    "last_pregcheck_date": last_preg_dt.isoformat() if last_preg_dt else None,
                    "last_pregcheck_result": ("pregnant" if last_preg_res is True else "not_pregnant" if last_preg_res is False else None),
                    "conception_service_date": conception_service.isoformat() if conception_service else None,
                    "days_open": int(days_open),
                    "service_period_days": int(service_period) if service_period is not None else None,
                }
            )

        # KPIs farm-level
        def _mean(xs: List[int]) -> float:
            if not xs:
                return float("nan")
            return float(sum(xs) / len(xs))

        add_kpi(tenant_id, farm_id, "repro_days_open_avg_open", _mean(open_days), "days", 0, ["dm_lactations", "dm_repro_events", "dm_animals"], notes=f"open cows dim>={vwp}")
        add_kpi(tenant_id, farm_id, "repro_days_open_avg_pregnant", _mean(preg_days), "days", 0, ["dm_lactations", "dm_repro_events"], notes=f"pregnant cows dim>={vwp}")
        add_kpi(tenant_id, farm_id, "repro_service_period_avg", _mean(sp_days), "days", 0, ["dm_lactations", "dm_repro_events"], notes="days from calving to first service")

        conc_rate = (successful_services_in_lb / services_in_lb) if services_in_lb else float("nan")
        add_kpi(tenant_id, farm_id, f"repro_conception_rate_{lb_conc}d", conc_rate, "share", lb_conc, ["dm_repro_events"], notes="success per service in lookback")

        preg_rate = (pregnancies_in_lb_pr / eligible_cows_pr) if eligible_cows_pr else float("nan")
        add_kpi(tenant_id, farm_id, f"repro_pregnancy_rate_{lb_pr}d", preg_rate, "share", lb_pr, ["dm_repro_events", "dm_lactations"], notes=f"pregnancies (conceptions) in last {lb_pr}d / eligible open cows")

        add_kpi(tenant_id, farm_id, "repro_eligible_open_cows", float(eligible_cows_pr), "count", 0, ["dm_animals", "dm_lactations"], notes=f"dim>={vwp} and not pregnant")
        add_kpi(tenant_id, farm_id, f"repro_pregnancies_conceived_{lb_pr}d", float(pregnancies_in_lb_pr), "count", lb_pr, ["dm_repro_events"], notes="conception service date within window")

    kpis_df = pd.DataFrame([r.__dict__ for r in kpi_rows])
    worklists_df = pd.DataFrame(wl_rows)
    cows_df = pd.DataFrame(cows_rows)

    # Sort worklists (priority ASC, due_date ASC, days_in_milk DESC)
    if not worklists_df.empty:
        worklists_df["_due"] = pd.to_datetime(worklists_df["due_date"], errors="coerce")
        worklists_df = worklists_df.sort_values([
            "worklist_type",
            "priority",
            "_due",
            "days_in_milk",
        ], ascending=[True, True, True, False]).drop(columns=["_due"])
    return kpis_df, worklists_df, cows_df


def run_repro_kpi_worklists(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    cfg_path: Path,
    repro_run: Optional[str] = None,
    input_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Materialize artifacts under artifacts/<dv>/repro/runs/<repro_run>/"""

    artifacts_root = Path(artifacts_root).resolve()
    dv = str(data_version)
    run_id = repro_run or new_repro_run_id()
    asof = pd.to_datetime(asof_date).date()

    if input_dir is None:
        # Prefer canonical layer, fallback to fixtures.
        cand = artifacts_root / dv / "canonical"
        if cand.exists():
            input_dir = cand
        else:
            input_dir = Path("data/fixtures/target_v2")
    input_dir = Path(input_dir).resolve()

    if not Path(cfg_path).exists():
        raise FileNotFoundError(f"cfg not found: {cfg_path}")
    cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8")) or {}

    out_dir = artifacts_root / dv / "repro" / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    kpis_df, wl_df, cows_df = compute_repro(input_dir=input_dir, asof_date=asof, cfg=cfg)

    kpis_csv = out_dir / "repro_kpis_farm.csv"
    worklists_csv = out_dir / "repro_worklists.csv"
    cows_csv = out_dir / "repro_cows_snapshot.csv"
    kpis_df.to_csv(kpis_csv, index=False)
    wl_df.to_csv(worklists_csv, index=False)
    cows_df.to_csv(cows_csv, index=False)

    # Excel export with sheets
    xlsx = out_dir / "repro_kpi_worklists.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        (kpis_df if not kpis_df.empty else pd.DataFrame(columns=[
            "tenant_id","farm_id","asof_date","kpi_id","value","unit","period_days","sources_json","notes"
        ])).to_excel(writer, sheet_name="kpis", index=False)
        if wl_df.empty:
            pd.DataFrame(columns=wl_df.columns.tolist() if len(wl_df.columns) else [
                "tenant_id","farm_id","asof_date","worklist_type","priority","animal_id","reason","next_action","due_date"
            ]).to_excel(writer, sheet_name="worklists", index=False)
        else:
            for t in ["insemination", "diagnostics", "repeat"]:
                sdf = wl_df[wl_df["worklist_type"] == t].copy()
                sdf.to_excel(writer, sheet_name=f"wl_{t}"[:31], index=False)
        cows_df.head(5000).to_excel(writer, sheet_name="cows_snapshot"[:31], index=False)

    # Manifest + checksums (small, deterministic)
    manifest = {
        "schema": "genomeai.run_manifest.v1",
        "step": "repro",
        "data_version": dv,
        "run_id": run_id,
        "created_at": _utc_ts(),
        "status": "DONE",
        "lineage": {"data_version": dv},
        "params": {
            "asof_date": asof.isoformat(),
            "input_dir": str(input_dir),
            "cfg_path": str(Path(cfg_path)),
        },
        "outputs": {
            "kpis_csv": str(kpis_csv),
            "worklists_csv": str(worklists_csv),
            "cows_snapshot_csv": str(cows_csv),
            "xlsx": str(xlsx),
        },
    }
    write_json(out_dir / "run_manifest.json", manifest)
    # Checksums
    sha: dict[str, str] = {}
    for p in [kpis_csv, worklists_csv, cows_csv, xlsx, out_dir / "run_manifest.json"]:
        if p.exists():
            sha[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
    write_json(out_dir / "checksums.json", {"sha256": sha, "generated_at": _utc_ts()})

    return {
        "ok": True,
        "data_version": dv,
        "repro_run": run_id,
        "asof_date": asof.isoformat(),
        "outputs": {
            "kpis_csv": str(kpis_csv),
            "worklists_csv": str(worklists_csv),
            "cows_snapshot_csv": str(cows_csv),
            "xlsx": str(xlsx),
        },
    }

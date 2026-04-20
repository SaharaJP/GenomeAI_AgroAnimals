from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd
import yaml

from core.application import find_latest_qc2_run, resolve_qc2_out_dir
from core.common.time import utc_isoformat_z, utc_timestamp_compact

from .versioning import ensure_run_dir, write_checksums, write_run_manifest


@dataclass
class VetDashboardInputs:
    """Inputs for Vet dashboard export.

    The UI must not implement business logic. It passes only parameters, while
    all calculations are performed here in offline-core.
    """

    data_version: str
    artifacts_dir: Path
    input_dir: Path
    asof_date: date
    qc_run: Optional[str] = None


def _load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def load_health_tables(*, input_dir: Path) -> Dict[str, pd.DataFrame]:
    """Load canonical health tables from an input directory.

    Expected files (CSV):
    - dm_animals.csv
    - dm_health_events.csv
    - dm_treatments.csv
    - dm_alerts.csv (optional)
    """

    input_dir = Path(input_dir)
    return {
        "animals": _load_csv(input_dir / "dm_animals.csv"),
        "health_events": _load_csv(input_dir / "dm_health_events.csv"),
        "treatments": _load_csv(input_dir / "dm_treatments.csv"),
        "alerts": _load_csv(input_dir / "dm_alerts.csv"),
    }


def _parse_date_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([pd.NaT] * len(df))
    return pd.to_datetime(df[col], errors="coerce").dt.date


def load_withdrawal_rules(path: Path = Path("configs/health/withdrawal_rules.yaml")) -> dict:
    if not path.exists():
        return {
            "version": "0",
            "default_withdrawal_days": 7,
            "treatment_types": {},
        }
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("withdrawal_rules.yaml must be a dict")
    obj.setdefault("default_withdrawal_days", 7)
    obj.setdefault("treatment_types", {})
    return obj


def compute_withdrawal_windows(
    treatments: pd.DataFrame,
    *,
    asof_date: date,
    rules: dict,
) -> pd.DataFrame:
    """Enrich treatments with calculated withdrawal windows.

    Rule (see docs/health/withdrawal_rules.md):
      last_admin_date = end_date if exists else start_date
      withdrawal_end_date_calc = last_admin_date + withdrawal_days

    If source provides withdrawal_end_date, it is treated as an explicit override.
    """

    if treatments.empty:
        return pd.DataFrame()

    df = treatments.copy()
    df["start_date"] = _parse_date_col(df, "start_date")
    df["end_date"] = _parse_date_col(df, "end_date")
    df["withdrawal_end_date"] = _parse_date_col(df, "withdrawal_end_date")

    tt = rules.get("treatment_types") or {}
    default_days = int(rules.get("default_withdrawal_days", 7) or 7)

    def _days_for_type(x: str) -> int:
        key = str(x or "").strip()
        obj = tt.get(key)
        if isinstance(obj, dict) and "withdrawal_days" in obj:
            try:
                return int(obj["withdrawal_days"])
            except Exception:
                return default_days
        return default_days

    df["withdrawal_days_rule"] = df.get("treatment_type", pd.Series([""] * len(df))).apply(_days_for_type)

    df["last_admin_date"] = df["end_date"].where(df["end_date"].notna(), df["start_date"])

    def _add_days(d: Optional[date], n: int) -> Optional[date]:
        if d is None or pd.isna(d):
            return None
        return d + timedelta(days=int(n))

    df["withdrawal_end_date_calc"] = [
        _add_days(d, n) for d, n in zip(df["last_admin_date"].tolist(), df["withdrawal_days_rule"].tolist())
    ]

    # mismatch flag only when both dates exist
    df["withdrawal_mismatch"] = (
        df["withdrawal_end_date"].notna()
        & df["withdrawal_end_date_calc"].notna()
        & (df["withdrawal_end_date"] != df["withdrawal_end_date_calc"])
    )

    # effective withdrawal end date: prefer explicit source, else calc
    df["withdrawal_end_date_effective"] = df["withdrawal_end_date"].where(
        df["withdrawal_end_date"].notna(), df["withdrawal_end_date_calc"]
    )

    # Normalize to python date (avoid Timestamp/date comparison issues)
    df["withdrawal_end_date_effective"] = pd.to_datetime(df["withdrawal_end_date_effective"], errors="coerce").dt.date

    df["withdrawal_active_asof"] = df["withdrawal_end_date_effective"].apply(
        lambda d: bool(pd.notna(d) and d >= asof_date)
    )

    return df


def registry_active_withdrawal_animals(
    *,
    treatments_enriched: pd.DataFrame,
    animals: pd.DataFrame,
) -> pd.DataFrame:
    if treatments_enriched.empty:
        return pd.DataFrame()
    df = treatments_enriched[treatments_enriched["withdrawal_active_asof"] == True].copy()  # noqa: E712
    if df.empty:
        return pd.DataFrame()
    cols = [c for c in ["tenant_id", "animal_id", "withdrawal_end_date_effective"] if c in df.columns]
    agg = (
        df[cols]
        .groupby([c for c in cols if c != "withdrawal_end_date_effective"], dropna=False)["withdrawal_end_date_effective"]
        .max()
        .reset_index()
        .rename(columns={"withdrawal_end_date_effective": "withdrawal_until"})
    )

    if not animals.empty and "animal_id" in animals.columns:
        join_cols = [c for c in ["animal_id", "farm_id", "ear_tag"] if c in animals.columns]
        agg = agg.merge(animals[join_cols], on="animal_id", how="left")
    return agg


def load_qc_alerts(
    *,
    artifacts_dir: Path,
    data_version: str,
    qc_run: Optional[str] = None,
) -> Tuple[Optional[str], pd.DataFrame, pd.DataFrame]:
    """Load QC v2 issues + auto alerts for a data_version.

    Supports both historical layout ``artifacts/qc2/<data_version>/<qc_run>`` and
    canonical layout ``artifacts/<data_version>/qc2/<qc_run>``.
    Returns (qc_run, qc_issues_df, qc_alerts_df). Missing artifacts -> empty frames.
    """

    qr = qc_run or find_latest_qc2_run(artifacts_root=artifacts_dir, data_version=data_version)
    if not qr:
        return None, pd.DataFrame(), pd.DataFrame()
    out_dir = resolve_qc2_out_dir(artifacts_root=artifacts_dir, data_version=data_version, qc_run=qr)
    if out_dir is None:
        return None, pd.DataFrame(), pd.DataFrame()
    issues = _load_csv(out_dir / "qc_issues.csv")
    alerts = _load_csv(out_dir / "alerts_auto.csv")
    return qr, issues, alerts


def build_inspection_list(
    *,
    animals: pd.DataFrame,
    alerts: pd.DataFrame,
    qc_issues: pd.DataFrame,
    qc_alerts: pd.DataFrame,
    active_withdrawal_animals: pd.DataFrame,
) -> pd.DataFrame:
    """Build a vet inspection list based on facts + risk alerts.

    No diagnoses are inferred here. The output is a list of animals and reasons:
    - health_risk alerts from dm_alerts (risk flags)
    - QC issues/alerts touching health datasets (data quality risks)
    - active withdrawal (operational restriction)
    """

    out_rows: list[dict] = []

    # Risk alerts (from data source)
    if (not alerts.empty) and ("alert_type" in alerts.columns):
        sub = alerts[alerts["alert_type"].astype(str) == "health_risk"].copy()
        if "entity_type" in sub.columns:
            sub = sub[sub["entity_type"].astype(str) == "animal"]
        for _, r in sub.iterrows():
            aid = str(r.get("entity_id", ""))
            if not aid:
                continue
            out_rows.append(
                {
                    "animal_id": aid,
                    "reason": "health_risk_alert",
                    "source": "dm_alerts",
                    "severity": str(r.get("severity", "")),
                    "message": str(r.get("message", "")),
                }
            )

    # QC issues specific to health datasets
    if (not qc_issues.empty) and ("dataset" in qc_issues.columns):
        sub = qc_issues[qc_issues["dataset"].astype(str).isin(["dm_health_events", "dm_treatments"])].copy()
        for _, r in sub.iterrows():
            rid = str(r.get("row_id", ""))
            # heuristics: row_id can be animal_id or contain it
            animal_id = rid.split("|")[-1] if rid else ""
            if not animal_id:
                continue
            out_rows.append(
                {
                    "animal_id": animal_id,
                    "reason": "qc_issue",
                    "source": "qc_v2",
                    "severity": str(r.get("severity", "")),
                    "message": str(r.get("message", "")),
                }
            )

    if (not qc_alerts.empty) and ("alert_type" in qc_alerts.columns):
        sub = qc_alerts[qc_alerts["alert_type"].astype(str).str.contains("qc", case=False, na=False)].copy()
        # entity_id may be row_id
        for _, r in sub.iterrows():
            rid = str(r.get("entity_id", ""))
            animal_id = rid.split("|")[-1] if rid else ""
            if not animal_id:
                continue
            out_rows.append(
                {
                    "animal_id": animal_id,
                    "reason": "qc_alert",
                    "source": "qc2.alerts_auto",
                    "severity": str(r.get("severity", "")),
                    "message": str(r.get("message", "")),
                }
            )

    # Active withdrawal
    if not active_withdrawal_animals.empty and "animal_id" in active_withdrawal_animals.columns:
        for _, r in active_withdrawal_animals.iterrows():
            aid = str(r.get("animal_id", ""))
            if not aid:
                continue
            until = r.get("withdrawal_until")
            out_rows.append(
                {
                    "animal_id": aid,
                    "reason": "active_withdrawal",
                    "source": "withdrawal_calc",
                    "severity": "info",
                    "message": f"withdrawal active until {until}",
                }
            )

    if not out_rows:
        return pd.DataFrame(columns=["animal_id", "reason", "source", "severity", "message", "farm_id", "ear_tag"])

    out = pd.DataFrame(out_rows)
    out = out.drop_duplicates(subset=["animal_id", "reason", "source", "message"], keep="first")

    if not animals.empty and "animal_id" in animals.columns:
        join_cols = [c for c in ["animal_id", "farm_id", "ear_tag"] if c in animals.columns]
        out = out.merge(animals[join_cols], on="animal_id", how="left")

    # Sort by severity (rough)
    sev_rank = {"critical": 0, "error": 1, "warn": 2, "major": 3, "minor": 4, "info": 5, "": 9}
    out["_sev_rank"] = out["severity"].astype(str).str.lower().map(lambda s: sev_rank.get(s, 8))
    out = out.sort_values(["_sev_rank", "animal_id"]).drop(columns=["_sev_rank"], errors="ignore")
    return out


def export_vet_registries(
    *,
    inputs: VetDashboardInputs,
    run_id: Optional[str] = None,
) -> Tuple[Path, Path]:
    """Export vet registries as XLSX.

    Returns (run_root, xlsx_path).
    """

    dv = inputs.data_version
    artifacts_dir = Path(inputs.artifacts_dir)
    asof = inputs.asof_date

    tables = load_health_tables(input_dir=inputs.input_dir)
    animals = tables["animals"]
    treatments = tables["treatments"]
    alerts = tables["alerts"]

    rules = load_withdrawal_rules()
    tr = compute_withdrawal_windows(treatments, asof_date=asof, rules=rules)
    active_animals = registry_active_withdrawal_animals(treatments_enriched=tr, animals=animals)

    qc_run, qc_issues, qc_alerts = load_qc_alerts(artifacts_dir=artifacts_dir, data_version=dv, qc_run=inputs.qc_run)
    insp = build_inspection_list(
        animals=animals,
        alerts=alerts,
        qc_issues=qc_issues,
        qc_alerts=qc_alerts,
        active_withdrawal_animals=active_animals,
    )

    dash_run = run_id or f"dash_{utc_timestamp_compact()}"
    run_root = ensure_run_dir(artifacts_dir, dv, dash_run)
    out_dir = run_root / "dashboards" / "vet_health_v2"
    out_dir.mkdir(parents=True, exist_ok=True)

    xlsx_path = out_dir / "vet_registries.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xw:
        (tables["health_events"] if not tables["health_events"].empty else pd.DataFrame()).to_excel(
            xw, index=False, sheet_name="health_events"
        )
        tr.to_excel(xw, index=False, sheet_name="treatments")
        active_animals.to_excel(xw, index=False, sheet_name="active_withdrawal_animals")
        insp.to_excel(xw, index=False, sheet_name="inspection_list")
        # raw alerts for transparency
        alerts.to_excel(xw, index=False, sheet_name="alerts_health_risk")
        qc_alerts.to_excel(xw, index=False, sheet_name="qc_alerts_auto")
        qc_issues.to_excel(xw, index=False, sheet_name="qc_issues")

    summary = {
        "schema": "genomeai.dashboard.vet_health_v2.v1",
        "data_version": dv,
        "run_id": dash_run,
        "created_at": utc_isoformat_z(),
        "asof_date": asof.isoformat(),
        "inputs": {
            "input_dir": str(Path(inputs.input_dir)),
            "qc_run": qc_run,
            "withdrawal_rules": "configs/health/withdrawal_rules.yaml",
        },
        "outputs": {
            "xlsx": str(xlsx_path.relative_to(run_root)),
        },
        "notes": "Vet dashboard export is built from canonical facts + configured withdrawal rules. No AI diagnoses.",
    }
    (out_dir / "dashboard_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "schema_version": "1.0",
        "data_version": dv,
        "run_id": dash_run,
        "step": "dashboard.vet_health_v2",
        "created_at": summary["created_at"],
        "inputs": summary["inputs"],
        "outputs": {
            "xlsx": str(xlsx_path.relative_to(run_root)),
            "dashboard_summary_json": str((out_dir / "dashboard_summary.json").relative_to(run_root)),
        },
        "lineage": {
            "qc_run": qc_run,
        },
    }
    write_checksums(run_root=run_root)
    write_run_manifest(run_root=run_root, manifest=manifest)
    write_checksums(run_root=run_root)
    return run_root, xlsx_path

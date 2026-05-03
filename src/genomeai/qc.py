from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from openpyxl import Workbook

from core.application import write_qc_output_bundle

from .contracts import DatasetContract, load_contracts_dir
from .versioning import generate_run_id, write_json, get_run_root, write_run_manifest, write_checksums, copy_tree_into_run


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _today_utc_date() -> datetime.date:
    return datetime.now(timezone.utc).date()


@dataclass
class QCIssue:
    dataset: str
    row_id: str
    severity: str  # PASS/WARN/ERROR (we only store WARN/ERROR rows here)
    check: str
    field: Optional[str]
    message: str
    sample_value: Optional[str] = None


def _row_id(dataset: str, df_index: int) -> str:
    # CSV has header row, so +2 approximates "line number" like in ingest.
    return f"{dataset}:{int(df_index) + 2}"


def _read_canonical_csv(canonical_dir: Path, dataset: str) -> pd.DataFrame:
    path = canonical_dir / f"{dataset}.csv"
    if not path.exists():
        raise FileNotFoundError(str(path))
    return pd.read_csv(path)


def _is_empty_value(x: Any) -> bool:
    if x is None:
        return True
    if isinstance(x, float) and pd.isna(x):
        return True
    s = str(x)
    return s.strip() == "" or s.strip().lower() == "nan"


def _required_field_issues(df: pd.DataFrame, contract: DatasetContract) -> Tuple[List[QCIssue], Dict[str, int]]:
    issues: List[QCIssue] = []
    metrics: Dict[str, int] = {}
    for fs in contract.fields:
        if not fs.required:
            continue
        if fs.name not in df.columns:
            metrics[f"required_missing_column:{fs.name}"] = int(len(df))
            for idx in df.index:
                issues.append(
                    QCIssue(
                        dataset=contract.dataset,
                        row_id=_row_id(contract.dataset, int(idx)),
                        severity="ERROR",
                        check="required_fields",
                        field=fs.name,
                        message="Required field is missing (column not present)",
                    )
                )
            continue

        s = df[fs.name]
        missing = s.isna() | (s.astype("string").str.strip() == "")
        cnt = int(missing.sum())
        metrics[f"required_empty:{fs.name}"] = cnt
        if cnt:
            for idx in missing[missing].index:
                issues.append(
                    QCIssue(
                        dataset=contract.dataset,
                        row_id=_row_id(contract.dataset, int(idx)),
                        severity="ERROR",
                        check="required_fields",
                        field=fs.name,
                        message="Required field is empty",
                    )
                )
    return issues, metrics


def _pk_issues(df: pd.DataFrame, contract: DatasetContract) -> Tuple[List[QCIssue], Dict[str, int]]:
    issues: List[QCIssue] = []
    metrics: Dict[str, int] = {}
    pk = list(contract.primary_key or [])
    if not pk:
        return issues, metrics

    # Missing PK parts
    miss_any = pd.Series(False, index=df.index)
    for f in pk:
        if f not in df.columns:
            # treat as missing for all rows
            miss_any = pd.Series(True, index=df.index)
            break
        miss_any = miss_any | df[f].isna() | (df[f].astype("string").str.strip() == "")
    miss_cnt = int(miss_any.sum())
    metrics["pk_missing_rows"] = miss_cnt
    for idx in miss_any[miss_any].index:
        issues.append(
            QCIssue(
                dataset=contract.dataset,
                row_id=_row_id(contract.dataset, int(idx)),
                severity="ERROR",
                check="primary_key",
                field=",".join(pk),
                message="Primary key value is missing",
            )
        )

    # Duplicates (ignore rows where any PK part is missing)
    dup_mask = pd.Series(False, index=df.index)
    if all(f in df.columns for f in pk):
        ok_pk = ~miss_any
        if bool(ok_pk.any()):
            dup_mask = df.loc[ok_pk].duplicated(subset=pk, keep=False)
            dup_idx = df.loc[ok_pk].index[dup_mask]
            metrics["pk_duplicate_rows"] = int(len(dup_idx))
            for idx in dup_idx:
                issues.append(
                    QCIssue(
                        dataset=contract.dataset,
                        row_id=_row_id(contract.dataset, int(idx)),
                        severity="ERROR",
                        check="primary_key",
                        field=",".join(pk),
                        message="Duplicate primary key",
                    )
                )
    else:
        metrics["pk_duplicate_rows"] = 0

    return issues, metrics


def _date_and_range_checks(
    animals: pd.DataFrame,
    lactations: pd.DataFrame,
    *,
    animals_contract: DatasetContract,
    lact_contract: DatasetContract,
) -> Tuple[List[QCIssue], Dict[str, int]]:
    issues: List[QCIssue] = []
    metrics: Dict[str, int] = {}

    today = _today_utc_date()

    # Parse dates
    b = pd.to_datetime(animals.get("birth_date"), errors="coerce") if "birth_date" in animals.columns else pd.Series(pd.NaT, index=animals.index)
    c = pd.to_datetime(lactations.get("calving_date"), errors="coerce") if "calving_date" in lactations.columns else pd.Series(pd.NaT, index=lactations.index)

    # calving_date <= today
    future_mask = c.dt.date > today
    metrics["calving_in_future_rows"] = int(future_mask.sum())
    for idx in future_mask[future_mask].index:
        issues.append(
            QCIssue(
                dataset=lact_contract.dataset,
                row_id=_row_id(lact_contract.dataset, int(idx)),
                severity="ERROR",
                check="date_validity",
                field="calving_date",
                message=f"calving_date is in the future (>{today.isoformat()})",
                sample_value=None if pd.isna(lactations.loc[idx, "calving_date"]) else str(lactations.loc[idx, "calving_date"]),
            )
        )

    # birth_date < calving_date (join by animal_id)
    if "animal_id" in lactations.columns and "animal_id" in animals.columns:
        animals_birth = animals[["animal_id"]].copy()
        animals_birth["_birth_dt"] = b
        birth_map = animals_birth.drop_duplicates(subset=["animal_id"]).set_index("animal_id")["_birth_dt"]

        birth_for_lact = lactations["animal_id"].map(birth_map)
        both = (~birth_for_lact.isna()) & (~c.isna())
        invalid = both & (birth_for_lact >= c)
        metrics["birth_ge_calving_rows"] = int(invalid.sum())
        for idx in invalid[invalid].index:
            issues.append(
                QCIssue(
                    dataset=lact_contract.dataset,
                    row_id=_row_id(lact_contract.dataset, int(idx)),
                    severity="ERROR",
                    check="date_validity",
                    field="birth_date,calving_date",
                    message="birth_date must be earlier than calving_date",
                    sample_value=f"birth={birth_for_lact.loc[idx].date().isoformat()}, calving={c.loc[idx].date().isoformat()}",
                )
            )
    else:
        metrics["birth_ge_calving_rows"] = 0

    # Missing calving_date (warn: can't validate rule)
    missing_calving = lactations.get("calving_date").isna() if "calving_date" in lactations.columns else pd.Series(True, index=lactations.index)
    missing_calving = missing_calving | (lactations.get("calving_date").astype("string").str.strip() == "") if "calving_date" in lactations.columns else missing_calving
    metrics["missing_calving_date_rows"] = int(missing_calving.sum())
    for idx in missing_calving[missing_calving].index:
        issues.append(
            QCIssue(
                dataset=lact_contract.dataset,
                row_id=_row_id(lact_contract.dataset, int(idx)),
                severity="WARN",
                check="date_validity",
                field="calving_date",
                message="calving_date is missing; date rules cannot be validated",
            )
        )

    # milk_305d_kg ranges/outliers (field name in contract)
    milk_field = "milk_305d_kg" if "milk_305d_kg" in lactations.columns else "milk_305_kg"
    if milk_field in lactations.columns:
        milk = pd.to_numeric(lactations[milk_field], errors="coerce")
        err = (milk.notna()) & ((milk < 0) | (milk > 25000))
        warn = (milk.notna()) & ((milk < 1000) | (milk > 18000)) & (~err)

        metrics["milk_range_error_rows"] = int(err.sum())
        metrics["milk_range_warn_rows"] = int(warn.sum())

        for idx in err[err].index:
            issues.append(
                QCIssue(
                    dataset=lact_contract.dataset,
                    row_id=_row_id(lact_contract.dataset, int(idx)),
                    severity="ERROR",
                    check="milk_305_range",
                    field=milk_field,
                    message="milk_305d_kg is outside hard limits [0, 25000]",
                    sample_value=str(lactations.loc[idx, milk_field]),
                )
            )
        for idx in warn[warn].index:
            issues.append(
                QCIssue(
                    dataset=lact_contract.dataset,
                    row_id=_row_id(lact_contract.dataset, int(idx)),
                    severity="WARN",
                    check="milk_305_range",
                    field=milk_field,
                    message="milk_305d_kg looks like an outlier (<1000 or >18000)",
                    sample_value=str(lactations.loc[idx, milk_field]),
                )
            )
    else:
        metrics["milk_range_error_rows"] = 0
        metrics["milk_range_warn_rows"] = 0

    return issues, metrics


def _connectivity_checks(
    animals: pd.DataFrame,
    lactations: pd.DataFrame,
    *,
    animals_contract: DatasetContract,
    lact_contract: DatasetContract,
) -> Tuple[List[QCIssue], Dict[str, int]]:
    issues: List[QCIssue] = []
    metrics: Dict[str, int] = {}

    if "animal_id" not in lactations.columns or "animal_id" not in animals.columns:
        metrics["lactations_missing_animal_rows"] = int(len(lactations))
        for idx in lactations.index:
            issues.append(
                QCIssue(
                    dataset=lact_contract.dataset,
                    row_id=_row_id(lact_contract.dataset, int(idx)),
                    severity="ERROR",
                    check="connectivity",
                    field="animal_id",
                    message="Cannot validate animals<->lactations: animal_id column missing",
                )
            )
        return issues, metrics

    animals_set = set(animals["animal_id"].dropna().astype("string").str.strip())
    lact_a = lactations["animal_id"].astype("string").str.strip()
    missing = (~lact_a.isna()) & (lact_a != "") & (~lact_a.isin(animals_set))
    metrics["lactations_missing_animal_rows"] = int(missing.sum())
    for idx in missing[missing].index:
        issues.append(
            QCIssue(
                dataset=lact_contract.dataset,
                row_id=_row_id(lact_contract.dataset, int(idx)),
                severity="ERROR",
                check="connectivity",
                field="animal_id",
                message="animal_id in lactations not found in dm_animals",
                sample_value=str(lactations.loc[idx, "animal_id"]),
            )
        )

    # Animals with no lactations (warn)
    lact_set = set(lact_a.dropna().astype("string").str.strip())
    a_ids = animals["animal_id"].astype("string").str.strip()
    no_lac = (~a_ids.isna()) & (a_ids != "") & (~a_ids.isin(lact_set))
    metrics["animals_without_lactations_rows"] = int(no_lac.sum())
    for idx in no_lac[no_lac].index:
        issues.append(
            QCIssue(
                dataset=animals_contract.dataset,
                row_id=_row_id(animals_contract.dataset, int(idx)),
                severity="WARN",
                check="connectivity",
                field="animal_id",
                message="animal has no lactations",
                sample_value=str(animals.loc[idx, "animal_id"]),
            )
        )

    return issues, metrics


def _overall_status(issues: List[QCIssue]) -> str:
    if any(i.severity == "ERROR" for i in issues):
        return "ERROR"
    if any(i.severity == "WARN" for i in issues):
        return "WARN"
    return "PASS"


def _write_xlsx_report(path: Path, *, status: str, summary: Dict[str, Any], issues: List[QCIssue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()

    # Summary sheet
    ws = wb.active
    ws.title = "Summary"
    ws.append(["qc_status", status])
    ws.append(["created_at_utc", summary.get("created_at_utc")])
    ws.append(["data_version", summary.get("data_version")])
    ws.append(["qc_run", summary.get("qc_run")])
    ws.append([])
    ws.append(["metric", "value"])
    for k, v in sorted(summary.get("metrics", {}).items()):
        ws.append([k, v])

    # Issues
    ws2 = wb.create_sheet("Issues")
    ws2.append(["dataset", "row_id", "severity", "check", "field", "message", "sample_value"])
    for i in issues:
        ws2.append([i.dataset, i.row_id, i.severity, i.check, i.field or "", i.message, i.sample_value or ""])

    wb.save(path)


def run_qc(
    *,
    data_version: str,
    artifacts_root: Path = Path("artifacts"),
    contracts_dir: Path = Path("configs/contracts"),
    qc_run: Optional[str] = None,
) -> Dict[str, Any]:
    """Run P0 QC on canonical layer for a given data_version.

    Outputs go to: artifacts/<data_version>/qc/<qc_run>/
    """
    artifacts_root = artifacts_root.resolve()
    contracts_dir = contracts_dir.resolve()

    contracts = load_contracts_dir(contracts_dir)
    required_ds = ["dm_farms", "dm_animals", "dm_lactations"]
    for ds in required_ds:
        if ds not in contracts:
            raise ValueError(f"Missing contract for required dataset: {ds}")

    base = artifacts_root / data_version
    canonical_dir = base / "canonical"
    if not canonical_dir.exists():
        raise FileNotFoundError(str(canonical_dir))

    qc_run_id = qc_run or generate_run_id(prefix="qc")
    out_dir = base / "qc" / qc_run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)

    issues: List[QCIssue] = []
    metrics: Dict[str, int] = {}
    datasets_loaded: Dict[str, int] = {}

    # Load canonical tables
    dfs: Dict[str, pd.DataFrame] = {}
    for ds in required_ds:
        try:
            df = _read_canonical_csv(canonical_dir, ds)
            dfs[ds] = df
            datasets_loaded[ds] = int(len(df))
        except FileNotFoundError:
            issues.append(
                QCIssue(
                    dataset=ds,
                    row_id=f"{ds}:NA",
                    severity="ERROR",
                    check="presence",
                    field=None,
                    message=f"Canonical file missing: {canonical_dir / (ds + '.csv')}",
                )
            )
            datasets_loaded[ds] = 0

    # Dataset-level checks (PK + required)
    for ds in required_ds:
        if ds not in dfs:
            continue
        c = contracts[ds]
        pk_iss, pk_met = _pk_issues(dfs[ds], c)
        rf_iss, rf_met = _required_field_issues(dfs[ds], c)
        issues.extend(pk_iss)
        issues.extend(rf_iss)
        metrics.update({f"{ds}.{k}": v for k, v in pk_met.items()})
        metrics.update({f"{ds}.{k}": v for k, v in rf_met.items()})

    # Cross-table checks
    if "dm_animals" in dfs and "dm_lactations" in dfs:
        date_iss, date_met = _date_and_range_checks(
            dfs["dm_animals"],
            dfs["dm_lactations"],
            animals_contract=contracts["dm_animals"],
            lact_contract=contracts["dm_lactations"],
        )
        conn_iss, conn_met = _connectivity_checks(
            dfs["dm_animals"],
            dfs["dm_lactations"],
            animals_contract=contracts["dm_animals"],
            lact_contract=contracts["dm_lactations"],
        )
        issues.extend(date_iss)
        issues.extend(conn_iss)
        metrics.update({f"cross.{k}": v for k, v in date_met.items()})
        metrics.update({f"cross.{k}": v for k, v in conn_met.items()})

    status = _overall_status(issues)

    config_version = "legacy_qc_contracts_v1"
    summary: Dict[str, Any] = {
        "schema": "genomeai.qc_summary.v1",
        "created_at_utc": _utc_now_iso(),
        "data_version": data_version,
        "qc_run": qc_run_id,
        "qc_status": status,
        "config_version": config_version,
        "config_path": str(contracts_dir),
        "datasets_loaded": datasets_loaded,
        "issue_counts": {},
        "row_counts": {},
        "metrics": metrics,
        "outputs": {},
    }

    issues_rows = []
    for i in issues:
        row = asdict(i)
        row["qc_run"] = qc_run_id
        row["data_version"] = data_version
        row["rule_id"] = str(row.get("check") or "legacy_qc")
        row["domain"] = str(row.get("dataset") or "general")
        row["remediation"] = "Исправить исходные данные и перезапустить QC"
        issues_rows.append(row)

    summary = write_qc_output_bundle(
        out_dir=out_dir,
        summary=summary,
        issues=issues_rows,
        alerts=[],
        include_alerts_csv=False,
        include_bad_rows_detailed=True,
        manifest_type="qc",
    )

    # Update qc manifest under artifacts/<data_version>/metadata/
    meta_dir = base / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = meta_dir / "qc_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"schema": "genomeai.qc_manifest.v1", "data_version": data_version, "runs": {}}
    manifest["runs"][qc_run_id] = {
        "created_at_utc": summary["created_at_utc"],
        "qc_status": status,
        "qc_summary": str((out_dir / "qc_summary.json").resolve()),
        "qc_report_xlsx": str((out_dir / "qc_report.xlsx").resolve()),
        "bad_rows_csv": str(Path(summary["outputs"]["bad_rows_csv"]).resolve()),
    }
    manifest["latest"] = qc_run_id
    write_json(manifest_path, manifest)

    # --- Target run layout (T0-03): materialize a run folder with manifest/checksums
    run_root = get_run_root(artifacts_root=artifacts_root, data_version=data_version, run_id=qc_run_id)
    copy_tree_into_run(src_dir=out_dir, run_root=run_root, subdir="qc")
    run_manifest = {
        "schema": "genomeai.run_manifest.v1",
        "step": "qc",
        "data_version": data_version,
        "run_id": qc_run_id,
        "created_at": summary["created_at_utc"],
        "status": summary["qc_status"],
        "outputs": {
            "legacy_dir": str(out_dir),
            "run_dir": str(run_root / "qc"),
            "qc_report_xlsx": str(out_dir / "qc_report.xlsx"),
            "bad_rows_csv": str(out_dir / "bad_rows.csv"),
        },
        "lineage": {
            "canonical_dir": str(base / "canonical"),
        },
    }
    write_run_manifest(run_root=run_root, manifest=run_manifest)
    write_checksums(run_root=run_root, include_subdirs=["qc"])

    return summary

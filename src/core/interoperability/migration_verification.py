from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from core.audit.events import write_audit
from core.infra.web_db import init_db
from core.interoperability.legacy_import import (
    _CONTRACT_DATASETS,
    _STAGE_SCHEMAS,
    _clean_optional_str,
    _normalized_frame,
)
from genomeai.contracts import load_contracts_dir
from genomeai.ingest import _coerce_field
from genomeai.versioning import write_json


_COMPARE_STATUS_ORDER = ("mismatch", "manual_review", "matched")
_SUPPORTED_DATASETS = ("animals", "lactations", "repro_events", "treatments", "basic_events", "health_events")


@dataclass(slots=True)
class MigrationVerificationIssue:
    dataset_key: str
    severity: str
    code: str
    message: str
    scope_kind: str = "global"
    scope_key: str = "all"
    metric_code: str | None = None
    legacy_value: Any = None
    new_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)



def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)



def _new_verification_run() -> str:
    return "mvfy_" + _utcnow().strftime("%Y%m%d_%H%M%S")



def _as_float(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None



def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()



def _clean_scope_value(value: Any) -> str:
    raw = _clean_str(value)
    return raw or "(blank)"



def _normalize_dataset_old(*, dataset_key: str, dataset_meta: Mapping[str, Any], project_root: Path) -> pd.DataFrame:
    source_file = Path(str(dataset_meta.get("source_file") or "")).resolve()
    mapping_file = Path(str(dataset_meta.get("mapping_file") or "")).resolve()
    if dataset_key in _CONTRACT_DATASETS:
        contracts = load_contracts_dir(Path(project_root) / "configs" / "contracts")
        contract = contracts[_CONTRACT_DATASETS[dataset_key]]
        field_names = list(contract.field_names)
        df_raw, df, meta = _normalized_frame(file_path=source_file, mapping_path=mapping_file, known_fields=field_names)
        _ = df_raw
        type_map = {str(field.name): str(field.type) for field in contract.fields}
        for field_name in field_names:
            coerced, _ok = _coerce_field(df, field_name, type_map.get(field_name, "string"), dayfirst=bool(meta.get("dayfirst")))
            df[field_name] = coerced
        return df[field_names].copy()
    schema = _STAGE_SCHEMAS[dataset_key]
    field_names = list(schema["field_types"].keys())
    _df_raw, df, meta = _normalized_frame(file_path=source_file, mapping_path=mapping_file, known_fields=field_names)
    for field_name, field_type in schema["field_types"].items():
        coerced, _ok = _coerce_field(df, field_name, field_type, dayfirst=bool(meta.get("dayfirst")))
        df[field_name] = coerced
    return df[field_names].copy()



def _normalize_dataset_new(*, dataset_key: str, dataset_meta: Mapping[str, Any]) -> pd.DataFrame:
    outputs = dict(dataset_meta.get("outputs") or {})
    path = outputs.get("canonical_csv") or outputs.get("staging_csv")
    if not path:
        return pd.DataFrame()
    csv_path = Path(str(path)).resolve()
    if not csv_path.exists():
        return pd.DataFrame()
    return pd.read_csv(csv_path)



def _animals_context(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["animal_id", "farm_id", "site_id", "pen_id", "pen_name", "status", "is_alive"])
    cols = [c for c in ("animal_id", "farm_id", "site_id", "pen_id", "pen_name", "status", "is_alive") if c in df.columns]
    out = df[cols].copy()
    for col in cols:
        if col != "is_alive":
            out[col] = out[col].map(_clean_optional_str)
    if "animal_id" in out.columns:
        out = out.sort_values([c for c in ("animal_id", "farm_id") if c in out.columns]).drop_duplicates("animal_id", keep="last")
    return out



def _enrich_with_animals_context(df: pd.DataFrame, animals_ctx: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if out.empty or animals_ctx.empty or "animal_id" not in out.columns:
        for col in ("farm_id", "site_id", "pen_id", "pen_name"):
            if col not in out.columns:
                out[col] = pd.NA
        return out
    ctx_cols = [c for c in ("animal_id", "farm_id", "site_id", "pen_id", "pen_name") if c in animals_ctx.columns]
    out = out.merge(animals_ctx[ctx_cols], on="animal_id", how="left", suffixes=("", "_ctx"))
    for col in ("farm_id", "site_id", "pen_id", "pen_name"):
        ctx_col = f"{col}_ctx"
        if ctx_col in out.columns:
            if col in out.columns:
                out[col] = out[col].where(out[col].notna() & (out[col].astype("string").str.strip() != ""), out[ctx_col])
                out = out.drop(columns=[ctx_col])
            else:
                out = out.rename(columns={ctx_col: col})
        elif col not in out.columns:
            out[col] = pd.NA
    return out



def _scope_groups(df: pd.DataFrame) -> dict[str, list[tuple[tuple[Any, ...], pd.DataFrame]]]:
    groups: dict[str, list[tuple[tuple[Any, ...], pd.DataFrame]]] = {"global": [(tuple(), df.copy())]}
    if df.empty:
        return groups
    work = df.copy()
    for col in ("farm_id", "site_id", "pen_id", "pen_name"):
        if col in work.columns:
            work[col] = work[col].map(_clean_optional_str)
    if "farm_id" in work.columns and work["farm_id"].notna().any():
        items = []
        for keys, sub in work.groupby(["farm_id"], dropna=False):
            items.append(((keys if isinstance(keys, tuple) else (keys,)), sub.copy()))
        groups["farm"] = items
    if "site_id" in work.columns and work["site_id"].notna().any():
        by = [c for c in ("farm_id", "site_id") if c in work.columns]
        items = []
        for keys, sub in work.groupby(by, dropna=False):
            items.append(((keys if isinstance(keys, tuple) else (keys,)), sub.copy()))
        groups["site"] = items
    if (("pen_id" in work.columns and work["pen_id"].notna().any()) or ("pen_name" in work.columns and work["pen_name"].notna().any())):
        by = [c for c in ("farm_id", "site_id") if c in work.columns]
        if "pen_id" in work.columns and work["pen_id"].notna().any():
            by.append("pen_id")
        elif "pen_name" in work.columns:
            by.append("pen_name")
        items = []
        for keys, sub in work.groupby(by, dropna=False):
            items.append(((keys if isinstance(keys, tuple) else (keys,)), sub.copy()))
        groups["group"] = items
    return groups



def _scope_record(scope_kind: str, keys: tuple[Any, ...], sample: pd.DataFrame | None = None) -> dict[str, Any]:
    sample = sample if sample is not None else pd.DataFrame()
    if scope_kind == "global":
        return {"scope_kind": "global", "scope_key": "all", "scope_label": "All records", "farm_id": None, "site_id": None, "pen_id": None, "pen_name": None}
    keys = tuple(keys)
    farm_id = site_id = pen_id = pen_name = None
    if scope_kind == "farm":
        farm_id = _clean_scope_value(keys[0] if keys else None)
        scope_key = f"farm:{farm_id}"
        scope_label = f"Farm {farm_id}"
    elif scope_kind == "site":
        farm_id = _clean_scope_value(keys[0] if len(keys) > 0 else None)
        site_id = _clean_scope_value(keys[1] if len(keys) > 1 else None)
        scope_key = f"site:{farm_id}/{site_id}"
        scope_label = f"Site {farm_id}/{site_id}"
    else:
        farm_id = _clean_scope_value(keys[0] if len(keys) > 0 else None)
        idx = 1
        if len(keys) >= 3:
            site_id = _clean_scope_value(keys[1])
            idx = 2
        if sample is not None and "pen_id" in sample.columns and (sample["pen_id"].notna().any() or len(keys) > idx):
            pen_id = _clean_scope_value(keys[idx] if len(keys) > idx else None)
        elif sample is not None and "pen_name" in sample.columns and (sample["pen_name"].notna().any() or len(keys) > idx):
            pen_name = _clean_scope_value(keys[idx] if len(keys) > idx else None)
        if (not pen_name or pen_name == '(blank)') and sample is not None and "pen_name" in sample.columns and sample["pen_name"].notna().any():
            pen_name = _clean_scope_value(sample["pen_name"].dropna().astype(str).iloc[0])
        pen_ref = pen_id or pen_name or "(blank)"
        scope_key = f"group:{farm_id}/{site_id or '-'}:{pen_ref}"
        scope_label = f"Group {farm_id}/{site_id or '-'}:{pen_ref}"
    return {
        "scope_kind": scope_kind,
        "scope_key": scope_key,
        "scope_label": scope_label,
        "farm_id": farm_id,
        "site_id": site_id,
        "pen_id": pen_id,
        "pen_name": pen_name,
    }



def _animals_metrics(df: pd.DataFrame) -> dict[str, Any]:
    out = {
        "headcount": int(df["animal_id"].astype("string").str.strip().replace("", pd.NA).dropna().nunique()) if "animal_id" in df.columns else None,
    }
    if "status" in df.columns:
        out["animals_status_active"] = int(df["status"].astype("string").str.lower().eq("active").sum())
    if "is_alive" in df.columns:
        alive = df["is_alive"]
        if alive.dtype == bool:
            out["animals_alive"] = int(alive.fillna(False).sum())
        else:
            out["animals_alive"] = int(alive.astype("string").str.lower().isin(["true", "1", "yes"]).sum())
    return out



def _lactations_metrics(df: pd.DataFrame) -> dict[str, Any]:
    out = {
        "lactations_total": int(len(df)),
        "animals_with_lactations": int(df["animal_id"].astype("string").str.strip().replace("", pd.NA).dropna().nunique()) if "animal_id" in df.columns else None,
    }
    milk_col = None
    for candidate in ("milk_305d_kg", "milk_305_kg"):
        if candidate in df.columns:
            milk_col = candidate
            break
    if milk_col:
        values = pd.to_numeric(df[milk_col], errors="coerce")
        out["avg_milk_305_kg"] = round(float(values.mean()), 3) if values.notna().any() else None
    return out



def _events_by_type_metrics(df: pd.DataFrame, *, prefix: str) -> dict[str, Any]:
    out = {f"{prefix}_total": int(len(df))}
    if "event_type" in df.columns:
        values = df["event_type"].astype("string").fillna("").str.strip().str.lower()
        for event_type, count in values[values != ""].value_counts().sort_index().items():
            out[f"{prefix}_type:{event_type}"] = int(count)
    return out



def _derive_repro_status_counts(df: pd.DataFrame) -> dict[str, int]:
    if df.empty or "animal_id" not in df.columns:
        return {}
    work = df.copy()
    work["event_date"] = pd.to_datetime(work.get("event_date"), errors="coerce")
    work["event_type_norm"] = work.get("event_type", pd.Series(dtype=object)).astype("string").fillna("").str.strip().str.lower()
    work["result_norm"] = work.get("result", pd.Series(dtype=object)).astype("string").fillna("").str.strip().str.lower()
    latest = work.sort_values(["animal_id", "event_date", "event_type_norm"], ascending=[True, False, True]).groupby("animal_id", as_index=False).head(1)

    def _status(row: pd.Series) -> str:
        et = _clean_str(row.get("event_type_norm")).lower()
        rs = _clean_str(row.get("result_norm")).lower()
        if et == "preg_check" and rs in {"positive", "pregnant", "confirmed", "yes"}:
            return "pregnant"
        if et == "preg_check" and rs in {"open", "negative", "not_pregnant", "no"}:
            return "open"
        if et in {"insemination", "insemination_done", "service", "breed", "bred"}:
            return "bred"
        return "other"

    statuses = latest.apply(_status, axis=1)
    counts = statuses.value_counts().to_dict()
    return {f"repro_status:{str(k)}": int(v) for k, v in counts.items()}



def _treatments_metrics(df: pd.DataFrame) -> dict[str, Any]:
    out = {"treatments_total": int(len(df))}
    if "end_date" in df.columns:
        end_date = pd.to_datetime(df["end_date"], errors="coerce")
        if end_date.notna().any():
            ref = end_date.max()
            out["active_treatments"] = int((end_date.isna() | (end_date >= ref)).sum())
        else:
            out["active_treatments"] = int(df["end_date"].isna().sum())
    return out



def _dataset_metrics(dataset_key: str, df: pd.DataFrame) -> dict[str, Any]:
    key = str(dataset_key)
    if key == "animals":
        return _animals_metrics(df)
    if key == "lactations":
        return _lactations_metrics(df)
    if key == "repro_events":
        out = _events_by_type_metrics(df, prefix="repro_events")
        out.update(_derive_repro_status_counts(df))
        return out
    if key == "basic_events":
        return _events_by_type_metrics(df, prefix="basic_events")
    if key == "health_events":
        return _events_by_type_metrics(df, prefix="health_events")
    if key == "treatments":
        return _treatments_metrics(df)
    return {f"{key}_rows": int(len(df))}



def _status_for_values(legacy_value: Any, new_value: Any) -> tuple[str, Any, str]:
    if legacy_value is None and new_value is None:
        return "manual_review", None, "Metric unavailable on both sides."
    if legacy_value is None or new_value is None:
        return "manual_review", None, "Metric unavailable on one side; manual check required."
    lf = _as_float(legacy_value)
    nf = _as_float(new_value)
    if lf is not None and nf is not None:
        diff = round(nf - lf, 6)
        status = "matched" if abs(diff) <= 1e-6 else "mismatch"
        return status, diff, ""
    status = "matched" if str(legacy_value) == str(new_value) else "mismatch"
    return status, None, ""



def _scope_metric_map(dataset_key: str, df: pd.DataFrame) -> dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]]:
    out: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    for scope_kind, groups in _scope_groups(df).items():
        for keys, sub in groups:
            scope_rec = _scope_record(scope_kind, keys, sample=sub)
            metrics = _dataset_metrics(dataset_key, sub)
            out[(scope_kind, scope_rec["scope_key"])] = (scope_rec, metrics)
    return out



def _compare_dataset_rows(*, dataset_key: str, legacy_df: pd.DataFrame, new_df: pd.DataFrame) -> list[dict[str, Any]]:
    legacy_map = _scope_metric_map(dataset_key, legacy_df)
    new_map = _scope_metric_map(dataset_key, new_df)
    scope_keys = sorted(set(legacy_map) | set(new_map), key=lambda x: (x[0], x[1]))
    rows: list[dict[str, Any]] = []
    for scope_key in scope_keys:
        scope_rec = dict((legacy_map.get(scope_key) or new_map.get(scope_key))[0])
        legacy_metrics = dict((legacy_map.get(scope_key) or ({}, {}))[1])
        new_metrics = dict((new_map.get(scope_key) or ({}, {}))[1])
        metric_codes = sorted(set(legacy_metrics) | set(new_metrics))
        for metric_code in metric_codes:
            lv = legacy_metrics.get(metric_code)
            nv = new_metrics.get(metric_code)
            status, diff, note = _status_for_values(lv, nv)
            rows.append({
                **scope_rec,
                "dataset_key": dataset_key,
                "metric_code": metric_code,
                "legacy_value": lv,
                "new_value": nv,
                "difference": diff,
                "status": status,
                "note": note,
            })
    return rows



def _issue_rows_from_bundle(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dataset_key, diag in dict(bundle.get("migration_diagnostics") or {}).items():
        for item in list(diag.get("issues") or []):
            rows.append({
                "dataset_key": dataset_key,
                "severity": item.get("severity"),
                "code": item.get("code"),
                "message": item.get("message"),
                "row": item.get("row"),
                "source_column": item.get("source_column"),
                "target_field": item.get("target_field"),
                "sample_value": item.get("sample_value"),
            })
    for msg in list((bundle.get("quality_reconciliation_summary") or {}).get("warnings") or []):
        rows.append({"dataset_key": "bundle", "severity": "warn", "code": "reconciliation_warning", "message": msg})
    orphan = dict((bundle.get("quality_reconciliation_summary") or {}).get("orphan_animal_refs") or {})
    for dataset_key, values in orphan.items():
        rows.append({"dataset_key": dataset_key, "severity": "error", "code": "orphan_animal_refs", "message": ", ".join([str(v) for v in values[:20]])})
    return rows



def _summary_rows(compare_rows: pd.DataFrame, issue_rows: pd.DataFrame, bundle: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    summary_rows: list[dict[str, Any]] = []
    status_counts = compare_rows["status"].value_counts().to_dict() if not compare_rows.empty else {}
    summary_rows.append({"metric": "matched", "value": int(status_counts.get("matched", 0))})
    summary_rows.append({"metric": "mismatch", "value": int(status_counts.get("mismatch", 0))})
    summary_rows.append({"metric": "manual_review", "value": int(status_counts.get("manual_review", 0))})
    summary_rows.append({"metric": "diagnostic_issues", "value": int(len(issue_rows))})

    dataset_rows: list[dict[str, Any]] = []
    datasets = sorted(set(compare_rows["dataset_key"].tolist()) | set((bundle.get("datasets") or {}).keys())) if not compare_rows.empty else sorted((bundle.get("datasets") or {}).keys())
    for dataset_key in datasets:
        sub = compare_rows[compare_rows["dataset_key"] == dataset_key] if not compare_rows.empty else pd.DataFrame()
        mism = int((sub["status"] == "mismatch").sum()) if not sub.empty else 0
        manual = int((sub["status"] == "manual_review").sum()) if not sub.empty else 0
        matched = int((sub["status"] == "matched").sum()) if not sub.empty else 0
        dataset_status = "matched"
        if mism > 0:
            dataset_status = "mismatch"
        elif manual > 0:
            dataset_status = "manual_review"
        dataset_rows.append({
            "dataset_key": dataset_key,
            "status": dataset_status,
            "matched": matched,
            "mismatch": mism,
            "manual_review": manual,
            "diagnostic_issues": int((issue_rows["dataset_key"] == dataset_key).sum()) if not issue_rows.empty else 0,
        })
    return summary_rows, dataset_rows



def _to_export_bytes(compare_rows: pd.DataFrame, dataset_rows: pd.DataFrame, issue_rows: pd.DataFrame, manifest: Mapping[str, Any], *, fmt: str) -> bytes:
    key = str(fmt or "csv").strip().lower()
    if key == "csv":
        return compare_rows.to_csv(index=False).encode("utf-8")
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        compare_rows.to_excel(writer, sheet_name="compare_rows", index=False)
        dataset_rows.to_excel(writer, sheet_name="dataset_status", index=False)
        issue_rows.to_excel(writer, sheet_name="issues", index=False)
        pd.DataFrame(list(manifest.get("summary_rows") or [])).to_excel(writer, sheet_name="summary", index=False)
    return bio.getvalue()



def list_migration_candidate_versions(*, artifacts_root: Path) -> list[str]:
    base = Path(artifacts_root).resolve()
    if not base.exists():
        return []
    out: list[str] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        if (child / "metadata" / "legacy_import_bundle.json").exists():
            out.append(child.name)
    return out



def list_migration_verification_runs(*, artifacts_root: Path, data_version: str) -> list[str]:
    root = Path(artifacts_root).resolve() / str(data_version) / "migration_verification"
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir() and (p / "verification_manifest.json").exists()])



def load_migration_verification_manifest(*, artifacts_root: Path, data_version: str, verification_run: str) -> dict[str, Any]:
    path = Path(artifacts_root).resolve() / str(data_version) / "migration_verification" / str(verification_run) / "verification_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))



def run_migration_verification_toolkit(
    *,
    project_root: Path,
    artifacts_root: Path,
    data_version: str,
    verification_run: str | None = None,
    db_path: Path | None = None,
    tenant_id: str = "default",
    user_id: int = 0,
    username: str = "system",
    role: str = "Admin",
    request_id: str | None = None,
) -> dict[str, Any]:
    root = Path(project_root).resolve()
    artifacts_root = Path(artifacts_root).resolve()
    verification_run = str(verification_run or _new_verification_run())
    bundle_path = artifacts_root / str(data_version) / "metadata" / "legacy_import_bundle.json"
    if not bundle_path.exists():
        raise FileNotFoundError(f"legacy import bundle not found for data_version={data_version}")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    old_frames: dict[str, pd.DataFrame] = {}
    new_frames: dict[str, pd.DataFrame] = {}
    for dataset_key, dataset_meta in dict(bundle.get("datasets") or {}).items():
        if dataset_key not in _SUPPORTED_DATASETS:
            continue
        old_frames[dataset_key] = _normalize_dataset_old(dataset_key=dataset_key, dataset_meta=dataset_meta, project_root=root)
        new_frames[dataset_key] = _normalize_dataset_new(dataset_key=dataset_key, dataset_meta=dataset_meta)

    old_animals_ctx = _animals_context(old_frames.get("animals", pd.DataFrame()))
    new_animals_ctx = _animals_context(new_frames.get("animals", pd.DataFrame()))
    compare_rows: list[dict[str, Any]] = []
    for dataset_key in sorted(set(old_frames) | set(new_frames)):
        old_df = _enrich_with_animals_context(old_frames.get(dataset_key, pd.DataFrame()), old_animals_ctx) if dataset_key != "animals" else old_frames.get(dataset_key, pd.DataFrame()).copy()
        new_df = _enrich_with_animals_context(new_frames.get(dataset_key, pd.DataFrame()), new_animals_ctx) if dataset_key != "animals" else new_frames.get(dataset_key, pd.DataFrame()).copy()
        compare_rows.extend(_compare_dataset_rows(dataset_key=dataset_key, legacy_df=old_df, new_df=new_df))

    compare_df = pd.DataFrame(compare_rows)
    if compare_df.empty:
        compare_df = pd.DataFrame(columns=["scope_kind", "scope_key", "scope_label", "farm_id", "site_id", "pen_id", "pen_name", "dataset_key", "metric_code", "legacy_value", "new_value", "difference", "status", "note"])
    else:
        compare_df["status_rank"] = compare_df["status"].map({k: i for i, k in enumerate(_COMPARE_STATUS_ORDER)}).fillna(99)
        compare_df = compare_df.sort_values(["status_rank", "scope_kind", "scope_key", "dataset_key", "metric_code"]).drop(columns=["status_rank"])

    issue_df = pd.DataFrame(_issue_rows_from_bundle(bundle))
    if issue_df.empty:
        issue_df = pd.DataFrame(columns=["dataset_key", "severity", "code", "message"])
    summary_rows, dataset_status_rows = _summary_rows(compare_df, issue_df, bundle)
    dataset_status_df = pd.DataFrame(dataset_status_rows)

    verification_dir = artifacts_root / str(data_version) / "migration_verification" / verification_run
    verification_dir.mkdir(parents=True, exist_ok=True)
    compare_csv = verification_dir / "compare_rows.csv"
    compare_xlsx = verification_dir / "compare_rows.xlsx"
    issues_csv = verification_dir / "issues.csv"
    dataset_status_csv = verification_dir / "dataset_status.csv"

    compare_df.to_csv(compare_csv, index=False, encoding="utf-8")
    dataset_status_df.to_csv(dataset_status_csv, index=False, encoding="utf-8")
    issue_df.to_csv(issues_csv, index=False, encoding="utf-8")
    xlsx_bytes = _to_export_bytes(compare_df, dataset_status_df, issue_df, {"summary_rows": summary_rows}, fmt="xlsx")
    compare_xlsx.write_bytes(xlsx_bytes)

    manifest = {
        "schema": "genomeai.migration_verification_toolkit.v1",
        "data_version": str(data_version),
        "verification_run": verification_run,
        "generated_at_utc": _utcnow().isoformat(),
        "legacy_import_bundle": str(bundle_path),
        "adapter_key": bundle.get("adapter_key"),
        "datasets": sorted(set(old_frames) | set(new_frames)),
        "summary_rows": summary_rows,
        "dataset_status_rows": dataset_status_rows,
        "outputs": {
            "compare_rows_csv": str(compare_csv),
            "compare_rows_xlsx": str(compare_xlsx),
            "issues_csv": str(issues_csv),
            "dataset_status_csv": str(dataset_status_csv),
        },
        "quality_reconciliation_summary": bundle.get("quality_reconciliation_summary") or {},
        "assumptions": [
            "Verification compares normalized legacy source exports against new canonical/staged outputs from the same data_version.",
            "Mismatches are never hidden; unavailable metrics are marked as manual_review.",
            "Site/group drilldown is shown only where source or reconciled animal context contains site_id / pen_id / pen_name.",
        ],
    }
    write_json(verification_dir / "verification_manifest.json", manifest)

    if db_path is not None:
        conn = sqlite3.connect(str(Path(db_path).resolve()))
        conn.row_factory = sqlite3.Row
        try:
            init_db(conn)
            write_audit(
                conn,
                tenant_id=str(tenant_id),
                user_id=int(user_id),
                username=str(username),
                role=str(role),
                action="migration.verification.run",
                object_type="migration_verification",
                object_id=verification_run,
                data_version=str(data_version),
                run_id=verification_run,
                request_id=request_id,
                after={
                    "adapter_key": bundle.get("adapter_key"),
                    "summary_rows": summary_rows,
                    "outputs": manifest["outputs"],
                },
            )
        finally:
            conn.close()

    return manifest


__all__ = [
    "list_migration_candidate_versions",
    "list_migration_verification_runs",
    "load_migration_verification_manifest",
    "run_migration_verification_toolkit",
]

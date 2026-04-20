from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml

from .contracts import DatasetContract
from .versioning import write_json


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


@dataclass
class IngestError:
    dataset: str
    source_file: str
    row: Optional[int]
    source_column: Optional[str]
    target_field: Optional[str]
    message: str
    sample_value: Optional[str] = None


def load_mapping_yaml(path: Path) -> Dict[str, Any]:
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("mapping yaml must be a dict")
    if "columns" not in obj or not isinstance(obj["columns"], dict):
        raise ValueError("mapping yaml must contain 'columns' mapping")
    return obj


def _normalize_bool_series(s: pd.Series) -> Tuple[pd.Series, pd.Series]:
    """Return (bool_series, ok_mask)."""
    def parse_one(x: Any) -> Optional[bool]:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        v = str(x).strip().lower()
        if v == "":
            return None
        if v in {"true", "1", "yes", "y", "t"}:
            return True
        if v in {"false", "0", "no", "n", "f"}:
            return False
        return "__INVALID__"  # type: ignore

    parsed = s.map(parse_one)
    ok_mask = ~(parsed == "__INVALID__")
    parsed = parsed.mask(parsed == "__INVALID__", pd.NA)
    return parsed.astype("boolean"), ok_mask


def _coerce_field(df: pd.DataFrame, field: str, typ: str, *, dayfirst: bool = False) -> Tuple[pd.Series, pd.Series]:
    """Return (coerced_series, ok_mask_for_non_null_inputs)."""
    s = df[field]
    non_null = ~s.isna() & (s.astype("string").str.strip() != "")

    if typ == "string":
        out = s.astype("string")
        return out, pd.Series([True] * len(df), index=df.index)

    if typ in {"int", "float"}:
        num = pd.to_numeric(s, errors="coerce")
        ok = (~num.isna()) | (~non_null)  # ok if parsed or input was null/empty
        if typ == "int":
            return num.round(0).astype("Int64"), ok
        return num.astype("Float64"), ok

    if typ in {"date", "datetime"}:
        dt = pd.to_datetime(s, errors="coerce", dayfirst=dayfirst)
        ok = (~dt.isna()) | (~non_null)
        if typ == "date":
            # canonical for csv: ISO date string
            out = dt.dt.strftime("%Y-%m-%d").astype("string")
            out = out.mask(dt.isna(), pd.NA)
            return out, ok
        return dt, ok

    if typ == "bool":
        b, ok = _normalize_bool_series(s)
        ok = ok | (~non_null)
        return b, ok

    # unknown type: keep as string
    out = s.astype("string")
    return out, pd.Series([True] * len(df), index=df.index)


def _read_tabular(file_path: Path, mapping: Dict[str, Any]) -> pd.DataFrame:
    suffix = file_path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        sheet = mapping.get("sheet_name", 0)
        return pd.read_excel(file_path, sheet_name=sheet)
    # csv
    return pd.read_csv(file_path, sep=None, engine="python")


def ingest_dataset(
    *,
    dataset_key: str,
    file_path: Path,
    mapping_path: Path,
    contract: DatasetContract,
    artifacts_root: Path,
    out_version: str,
    max_error_examples: int = 200,
) -> Dict[str, Any]:
    """Ingest external file into canonical layer for a single dataset.

    Returns a summary dict.
    """
    file_path = file_path.resolve()
    mapping_path = mapping_path.resolve()
    artifacts_root = artifacts_root.resolve()

    mapping = load_mapping_yaml(mapping_path)
    dayfirst = bool(mapping.get("dayfirst", False))
    df_raw = _read_tabular(file_path, mapping)
    df_raw.columns = [str(c).strip() for c in df_raw.columns]

    errors: List[IngestError] = []

    def remaining_examples() -> int:
        # log up to max_error_examples row-level examples (file-level errors don't count)
        row_level = sum(1 for e in errors if e.row is not None)
        return max(0, int(max_error_examples) - row_level)

    dayfirst = bool(mapping.get("dayfirst", False))

    # Column mapping
    col_map: Dict[str, str] = {str(k): str(v) for k, v in mapping.get("columns", {}).items()}
    missing_source_cols = [c for c in col_map.keys() if c not in set(df_raw.columns)]
    for c in missing_source_cols:
        errors.append(
            IngestError(
                dataset=contract.dataset,
                source_file=str(file_path),
                row=None,
                source_column=c,
                target_field=col_map.get(c),
                message="Missing source column in input file",
            )
        )

    df = df_raw.rename(columns=col_map)

    # Add constants
    constants = mapping.get("constants", {})
    if constants and isinstance(constants, dict):
        for k, v in constants.items():
            df[str(k)] = v

    # Build canonical frame with contract columns only
    for fs in contract.fields:
        if fs.name not in df.columns:
            df[fs.name] = pd.NA
    df = df[contract.field_names]

    # Type normalization + per-row conversion errors
    for fs in contract.fields:
        coerced, ok_mask = _coerce_field(df, fs.name, fs.type, dayfirst=dayfirst)
        # identify conversion failures only where input was non-empty
        bad_idx = ok_mask[~ok_mask].index
        rem = remaining_examples()
        if len(bad_idx) > 0 and rem > 0:
            for idx in bad_idx[:rem]:
                val = df.loc[idx, fs.name]
                errors.append(
                    IngestError(
                        dataset=contract.dataset,
                        source_file=str(file_path),
                        row=int(idx) + 2,  # best-effort: like csv row number
                        source_column=None,
                        target_field=fs.name,
                        message=f"Failed to coerce value to type '{fs.type}'",
                        sample_value=None if pd.isna(val) else str(val),
                    )
                )
        df[fs.name] = coerced

    # Required fields empty
    for fs in contract.fields:
        if not fs.required:
            continue
        missing = df[fs.name].isna() | (df[fs.name].astype("string").str.strip() == "")
        rem = remaining_examples()
        if bool(missing.any()) and rem > 0:
            for idx in missing[missing].index[:rem]:
                errors.append(
                    IngestError(
                        dataset=contract.dataset,
                        source_file=str(file_path),
                        row=int(idx) + 2,
                        source_column=None,
                        target_field=fs.name,
                        message="Required field is empty after mapping/coercion",
                        sample_value=None,
                    )
                )

    # Prepare output structure
    base = artifacts_root / out_version
    canonical_dir = base / "canonical"
    logs_dir = base / "ingest_logs"
    meta_dir = base / "metadata"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    out_csv = canonical_dir / f"{contract.dataset}.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")

    out_parquet: Optional[Path] = None
    try:
        out_parquet = canonical_dir / f"{contract.dataset}.parquet"
        df.to_parquet(out_parquet, index=False)
    except Exception:
        out_parquet = None

    # Write errors jsonl
    err_path = logs_dir / f"{contract.dataset}_errors.jsonl"
    with err_path.open("w", encoding="utf-8") as f:
        for e in errors:
            f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")

    summary: Dict[str, Any] = {
        "schema": "genomeai.ingest_summary.v1",
        "created_at_utc": _utc_now_iso(),
        "dataset_key": dataset_key,
        "dataset": contract.dataset,
        "contract_version": contract.contract_version,
        "source_file": str(file_path),
        "source_file_sha256": _sha256_file(file_path),
        "mapping_file": str(mapping_path),
        "mapping_sha256": _sha256_file(mapping_path),
        "out_version": out_version,
        "canonical_csv": str(out_csv),
        "canonical_parquet": str(out_parquet) if out_parquet else None,
        "rows_in": int(len(df_raw)),
        "rows_out": int(len(df)),
        "error_count": int(len(errors)),
        "error_examples_logged": int(len(errors)),
    }

    write_json(meta_dir / f"ingest_{contract.dataset}.json", summary)

    # Update manifest
    manifest_path = meta_dir / "ingest_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "schema": "genomeai.ingest_manifest.v1",
            "out_version": out_version,
            "datasets": {},
        }
    manifest["datasets"][contract.dataset] = {
        "updated_at_utc": summary["created_at_utc"],
        "contract_version": summary["contract_version"],
        "source_file": summary["source_file"],
        "mapping_file": summary["mapping_file"],
        "rows_out": summary["rows_out"],
        "error_count": summary["error_count"],
        "canonical_csv": summary["canonical_csv"],
        "canonical_parquet": summary["canonical_parquet"],
    }
    write_json(manifest_path, manifest)

    return summary

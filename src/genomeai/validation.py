from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .contracts import DatasetContract


@dataclass
class ValidationError:
    dataset: str
    file: str
    row: Optional[int]
    field: Optional[str]
    message: str

    def __str__(self) -> str:
        loc = []
        if self.row is not None:
            loc.append(f"row={self.row}")
        if self.field:
            loc.append(f"field={self.field}")
        loc_str = (" " + ",".join(loc)) if loc else ""
        return f"[{self.dataset}] {self.file}{loc_str}: {self.message}"


def _parse_bool(v: str) -> bool:
    vv = v.strip().lower()
    if vv in {"true", "1", "yes", "y"}:
        return True
    if vv in {"false", "0", "no", "n"}:
        return False
    raise ValueError("not a bool")


def _parse_date(v: str) -> date:
    return date.fromisoformat(v.strip())


def _parse_value(v: str, typ: str):
    if typ == "string":
        return v
    if typ == "int":
        return int(v)
    if typ == "float":
        return float(v)
    if typ == "bool":
        return _parse_bool(v)
    if typ == "date":
        return _parse_date(v)
    return v


def validate_csv(file_path: Path, contract: DatasetContract, dataset: str) -> List[ValidationError]:
    errors: List[ValidationError] = []
    with file_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return [ValidationError(dataset, str(file_path), None, None, "Empty CSV or missing header")]
        header = [h.strip() for h in reader.fieldnames]

        for req in contract.required_fields:
            if req not in header:
                errors.append(ValidationError(dataset, str(file_path), None, req, "Missing required column"))

        for i, row in enumerate(reader, start=2):
            for fs in contract.fields:
                raw = (row.get(fs.name) or "").strip()
                if fs.required and raw == "":
                    errors.append(ValidationError(dataset, str(file_path), i, fs.name, "Required value is empty"))
                    continue
                if raw == "":
                    continue

                try:
                    _parse_value(raw, fs.type)
                except Exception:
                    errors.append(ValidationError(dataset, str(file_path), i, fs.name, f"Value '{raw}' is not {fs.type}"))
                    continue

                if fs.allowed_values is not None and raw not in set(fs.allowed_values):
                    errors.append(ValidationError(dataset, str(file_path), i, fs.name, f"Value '{raw}' not in allowed_values={fs.allowed_values}"))
    return errors


def validate_input_dir(input_path: Path, contracts: Dict[str, DatasetContract]) -> Tuple[List[ValidationError], Dict[str, Path]]:
    found: Dict[str, Path] = {}
    errors: List[ValidationError] = []

    # Optional datasets: absence must not fail the whole validation.
    # Rationale: web dashboards gracefully degrade if optional marts are not provided.
    OPTIONAL_DATASETS = {
        "dm_testday",
        "dm_health_events",
        "dm_treatments",
    }

    for dataset, contract in contracts.items():
        expected = input_path / f"{dataset}.csv"
        if expected.exists():
            found[dataset] = expected
            errors.extend(validate_csv(expected, contract, dataset))
        else:
            if dataset in OPTIONAL_DATASETS:
                continue
            errors.append(ValidationError(dataset, str(expected), None, None, "Missing required dataset file"))

    return errors, found

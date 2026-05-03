from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from .contracts import DatasetContract
from .ingest import _coerce_field, _read_tabular, load_mapping_yaml


@dataclass
class ContractValidationIssue:
    dataset: str
    dataset_key: str
    source_file: str
    row: int | None
    source_column: str | None
    target_field: str | None
    message: str
    sample_value: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_human_text(self) -> str:
        parts: list[str] = [self.dataset]
        if self.row is not None:
            parts.append(f"строка {self.row}")
        if self.source_column:
            parts.append(f"колонка {self.source_column}")
        if self.target_field:
            parts.append(f"поле {self.target_field}")
        prefix = " · ".join(parts)
        if self.sample_value not in (None, ""):
            return f"{prefix}: {self.message} (пример: {self.sample_value})"
        return f"{prefix}: {self.message}"


@dataclass
class ContractValidationResult:
    ok: bool
    dataset: str
    dataset_key: str
    contract_version: str
    source_file: str
    mapping_file: str
    rows_in: int
    issues: List[ContractValidationIssue]

    @property
    def error_count(self) -> int:
        return len(self.issues)

    def top_messages(self, limit: int = 10) -> List[str]:
        return [issue.to_human_text() for issue in self.issues[: max(0, int(limit))]]

    def to_dict(self, *, preview_limit: int = 20) -> dict[str, Any]:
        return {
            "schema": "genomeai.contract_validation_result.v1",
            "ok": self.ok,
            "dataset": self.dataset,
            "dataset_key": self.dataset_key,
            "contract_version": self.contract_version,
            "source_file": self.source_file,
            "mapping_file": self.mapping_file,
            "rows_in": self.rows_in,
            "error_count": self.error_count,
            "preview": self.top_messages(limit=preview_limit),
            "issues": [issue.to_dict() for issue in self.issues[: max(0, int(preview_limit))]],
        }


def validate_source_by_contract(
    *,
    dataset_key: str,
    file_path: Path,
    mapping_path: Path,
    contract: DatasetContract,
    max_issues: int = 50,
) -> ContractValidationResult:
    file_path = file_path.resolve()
    mapping_path = mapping_path.resolve()
    mapping = load_mapping_yaml(mapping_path)
    dayfirst = bool(mapping.get("dayfirst", False))
    df_raw = _read_tabular(file_path, mapping)
    df_raw.columns = [str(c).strip() for c in df_raw.columns]

    issues: List[ContractValidationIssue] = []

    def remaining() -> int:
        return max(0, int(max_issues) - len(issues))

    def add_issue(
        *,
        row: int | None,
        source_column: str | None,
        target_field: str | None,
        message: str,
        sample_value: Any = None,
    ) -> None:
        if remaining() <= 0:
            return
        issues.append(
            ContractValidationIssue(
                dataset=contract.dataset,
                dataset_key=str(dataset_key),
                source_file=str(file_path),
                row=row,
                source_column=source_column,
                target_field=target_field,
                message=message,
                sample_value=None if sample_value is None or pd.isna(sample_value) else str(sample_value),
            )
        )

    col_map: Dict[str, str] = {str(k): str(v) for k, v in (mapping.get("columns") or {}).items()}
    source_cols = set(df_raw.columns)
    missing_source_cols = [c for c in col_map.keys() if c not in source_cols]
    for src_col in missing_source_cols:
        add_issue(
            row=None,
            source_column=src_col,
            target_field=col_map.get(src_col),
            message="Колонка из mapping не найдена во входном файле",
        )

    target_counts: Dict[str, int] = {}
    for src_col, target_field in col_map.items():
        target_counts[target_field] = target_counts.get(target_field, 0) + 1
    duplicate_targets = sorted(target for target, count in target_counts.items() if count > 1)
    for target_field in duplicate_targets:
        add_issue(
            row=None,
            source_column=None,
            target_field=target_field,
            message="В mapping несколько исходных колонок пишут в одно и то же поле канона",
        )

    df = df_raw.rename(columns=col_map)
    constants = mapping.get("constants", {})
    if isinstance(constants, dict):
        for key, value in constants.items():
            df[str(key)] = value

    present_target_fields = set(df.columns)
    structurally_missing_required = [field for field in contract.required_fields if field not in present_target_fields]
    for target_field in structurally_missing_required:
        add_issue(
            row=None,
            source_column=None,
            target_field=target_field,
            message="Обязательное поле контракта не заполняется mapping/константами",
        )

    for field in contract.fields:
        if field.name not in df.columns:
            df[field.name] = pd.NA
    df = df[contract.field_names]

    for field in contract.fields:
        raw_before = df[field.name].copy()
        coerced, ok_mask = _coerce_field(df, field.name, field.type, dayfirst=dayfirst)
        bad_idx = ok_mask[~ok_mask].index
        if len(bad_idx) > 0 and remaining() > 0:
            for idx in bad_idx[: remaining()]:
                add_issue(
                    row=int(idx) + 2,
                    source_column=None,
                    target_field=field.name,
                    message=f"Значение не приводится к типу {field.type}",
                    sample_value=raw_before.loc[idx],
                )
        df[field.name] = coerced

        if field.allowed_values:
            allowed = {str(v) for v in field.allowed_values}
            mask_non_null = ~(df[field.name].isna() | (df[field.name].astype("string").str.strip() == ""))
            bad_allowed = df.index[mask_non_null & ~df[field.name].astype("string").isin(allowed)]
            if len(bad_allowed) > 0 and remaining() > 0:
                for idx in bad_allowed[: remaining()]:
                    add_issue(
                        row=int(idx) + 2,
                        source_column=None,
                        target_field=field.name,
                        message=f"Значение вне allowed_values={sorted(allowed)}",
                        sample_value=df.loc[idx, field.name],
                    )

    for field in contract.fields:
        if not field.required:
            continue
        missing_mask = df[field.name].isna() | (df[field.name].astype("string").str.strip() == "")
        if bool(missing_mask.any()) and remaining() > 0:
            for idx in missing_mask[missing_mask].index[: remaining()]:
                add_issue(
                    row=int(idx) + 2,
                    source_column=None,
                    target_field=field.name,
                    message="Обязательное поле пустое после mapping/нормализации",
                )

    return ContractValidationResult(
        ok=not issues,
        dataset=contract.dataset,
        dataset_key=str(dataset_key),
        contract_version=contract.contract_version,
        source_file=str(file_path),
        mapping_file=str(mapping_path),
        rows_in=int(len(df_raw)),
        issues=issues,
    )

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    required: bool
    allowed_values: Optional[List[str]] = None
    description: str = ""


@dataclass(frozen=True)
class DatasetContract:
    dataset: str
    contract_version: str
    description: str
    fields: List[FieldSpec]
    primary_key: Optional[List[str]] = None
    foreign_keys: Optional[List[dict]] = None
    notes: Optional[List[str]] = None

    @property
    def required_fields(self) -> List[str]:
        return [f.name for f in self.fields if f.required]

    @property
    def field_names(self) -> List[str]:
        return [f.name for f in self.fields]


def load_contract(path: Path) -> DatasetContract:
    raw = json.loads(path.read_text(encoding="utf-8"))
    fields: List[FieldSpec] = []
    for f in raw.get("fields", []):
        fields.append(
            FieldSpec(
                name=f["name"],
                type=f["type"],
                required=bool(f.get("required", False)),
                allowed_values=f.get("allowed_values"),
                description=f.get("description", ""),
            )
        )
    return DatasetContract(
        dataset=raw["dataset"],
        contract_version=raw.get("contract_version", "0.0.0"),
        description=raw.get("description", ""),
        fields=fields,
        primary_key=raw.get("primary_key"),
        foreign_keys=raw.get("foreign_keys"),
        notes=raw.get("notes"),
    )


def load_contracts_dir(contracts_dir: Path) -> Dict[str, DatasetContract]:
    result: Dict[str, DatasetContract] = {}
    for p in sorted(contracts_dir.glob("*.json")):
        raw = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "dataset" not in raw or "fields" not in raw:
            continue
        c = load_contract(p)
        result[c.dataset] = c
    return result

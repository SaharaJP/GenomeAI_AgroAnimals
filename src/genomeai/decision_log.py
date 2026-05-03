from __future__ import annotations

import csv
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from core.domain import DecisionRecord, decision_record_to_legacy_dict


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def decisions_dir(artifacts_root: Path, data_version: str) -> Path:
    return artifacts_root / data_version / "decisions"


def decision_log_paths(artifacts_root: Path, data_version: str) -> Dict[str, Path]:
    base = decisions_dir(artifacts_root, data_version)
    return {
        "csv": base / "decision_log.csv",
        "xlsx": base / "decision_log.xlsx",
        "jsonl": base / "decision_log.jsonl",
    }


CSV_COLUMNS: List[str] = [
    "created_at_utc",
    "user",
    "animal_id",
    "lactation_id",
    "recommendation_type",
    "decision",
    "comment",
    "lactation_no",
    "farm_id",
    "scoring_run",
]


def _ensure_empty_files(paths: Dict[str, Path]) -> None:
    for p in paths.values():
        p.parent.mkdir(parents=True, exist_ok=True)

    # CSV header
    csv_path = paths["csv"]
    if not csv_path.exists():
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            w.writeheader()

    # JSONL
    jsonl_path = paths["jsonl"]
    if not jsonl_path.exists():
        jsonl_path.write_text("", encoding="utf-8")


def _write_xlsx_from_csv(csv_path: Path, xlsx_path: Path) -> None:
    df = pd.read_csv(csv_path)
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name="decision_log")
    _canonicalize_xlsx(xlsx_path)


_FIXED_XLSX_W3CDTF = "2000-01-01T00:00:00Z"
_FIXED_ZIP_DT = (2000, 1, 1, 0, 0, 0)
_CORE_CREATED_RE = re.compile(r"(<dcterms:created[^>]*>)(.*?)(</dcterms:created>)")
_CORE_MODIFIED_RE = re.compile(r"(<dcterms:modified[^>]*>)(.*?)(</dcterms:modified>)")


def _normalize_core_xml(xml_bytes: bytes) -> bytes:
    text = xml_bytes.decode("utf-8")
    text = _CORE_CREATED_RE.sub(rf"\1{_FIXED_XLSX_W3CDTF}\3", text)
    text = _CORE_MODIFIED_RE.sub(rf"\1{_FIXED_XLSX_W3CDTF}\3", text)
    return text.encode("utf-8")


def _canonicalize_xlsx(path: Path) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(path, "r") as src:
        names = sorted(src.namelist())
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as dst:
            for name in names:
                payload = src.read(name)
                if name == "docProps/core.xml":
                    payload = _normalize_core_xml(payload)
                info = zipfile.ZipInfo(filename=name, date_time=_FIXED_ZIP_DT)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 0
                info.external_attr = 0o600 << 16
                dst.writestr(info, payload)
    tmp_path.replace(path)


def init_decision_log(
    artifacts_root: Path,
    data_version: str,
    scoring_run: Optional[str] = None,
    user: str = "unknown",
    template_from_scoring: bool = True,
    template_created_at_utc: Optional[str] = None,
) -> Dict[str, str]:
    """Create decision_log.{csv,xlsx,jsonl}. Optionally pre-fill template rows from scoring output.

    Object identity per requirement: animal_id + lactation_id + recommendation_type.
    If a real lactation_id is absent in P0 contracts, we use lactation_id = f"{animal_id}__{lactation_no}".
    """
    paths = decision_log_paths(artifacts_root, data_version)
    _ensure_empty_files(paths)

    # Optionally pre-fill from scoring
    if template_from_scoring and scoring_run:
        scored_path = artifacts_root / data_version / "scoring" / scoring_run / "scored_latest.csv"
        if scored_path.exists():
            df = pd.read_csv(scored_path)
            needed = {"animal_id", "lactation_no", "action"}
            if needed.issubset(set(df.columns)):
                existing = pd.read_csv(paths["csv"])
                existing_keys = set(
                    zip(
                        existing.get("animal_id", []),
                        existing.get("lactation_id", []),
                        existing.get("recommendation_type", []),
                    )
                )

                new_rows: List[Dict[str, object]] = []
                created_at_utc = str(template_created_at_utc or _utc_now_iso())
                for _, r in df.iterrows():
                    animal_id = str(r.get("animal_id"))
                    lact_no = r.get("lactation_no")
                    rec_type = str(r.get("action"))
                    lact_id = f"{animal_id}__{int(lact_no)}" if pd.notna(lact_no) else f"{animal_id}__NA"
                    key = (animal_id, lact_id, rec_type)
                    if key in existing_keys:
                        continue
                    new_rows.append(
                        {
                            "created_at_utc": created_at_utc,
                            "user": user,
                            "animal_id": animal_id,
                            "lactation_id": lact_id,
                            "recommendation_type": rec_type,
                            "decision": "",
                            "comment": "",
                            "lactation_no": int(lact_no) if pd.notna(lact_no) else "",
                            "farm_id": str(r.get("farm_id")) if "farm_id" in df.columns and pd.notna(r.get("farm_id")) else "",
                            "scoring_run": scoring_run,
                        }
                    )

                if new_rows:
                    # append to CSV
                    with paths["csv"].open("a", newline="", encoding="utf-8") as f:
                        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
                        for row in new_rows:
                            w.writerow(row)

                    # append to JSONL
                    with paths["jsonl"].open("a", encoding="utf-8") as f:
                        for row in new_rows:
                            rec = DecisionRecord(schema="genomeai.decision_record.v1", **row)
                            f.write(json.dumps(decision_record_to_legacy_dict(rec), ensure_ascii=False) + "\n")

    # Always write XLSX export
    _write_xlsx_from_csv(paths["csv"], paths["xlsx"])
    return {k: str(v.resolve()) for k, v in paths.items()}


def add_decision(
    artifacts_root: Path,
    data_version: str,
    animal_id: str,
    lactation_id: str,
    recommendation_type: str,
    decision: str,
    comment: str,
    user: str,
    lactation_no: Optional[int] = None,
    farm_id: Optional[str] = None,
    scoring_run: Optional[str] = None,
) -> Tuple[bool, str]:
    paths = decision_log_paths(artifacts_root, data_version)
    _ensure_empty_files(paths)

    row = {
        "created_at_utc": _utc_now_iso(),
        "user": user,
        "animal_id": str(animal_id),
        "lactation_id": str(lactation_id),
        "recommendation_type": str(recommendation_type),
        "decision": str(decision),
        "comment": str(comment),
        "lactation_no": int(lactation_no) if lactation_no is not None else "",
        "farm_id": str(farm_id) if farm_id is not None else "",
        "scoring_run": str(scoring_run) if scoring_run is not None else "",
    }

    with paths["csv"].open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writerow(row)

    with paths["jsonl"].open("a", encoding="utf-8") as f:
        rec = DecisionRecord(schema="genomeai.decision_record.v1", **row)
        f.write(json.dumps(decision_record_to_legacy_dict(rec), ensure_ascii=False) + "\n")

    _write_xlsx_from_csv(paths["csv"], paths["xlsx"])
    return True, "OK"

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


def utc_ts() -> str:
    # ISO 8601 without microseconds for human readability
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass(frozen=True)
class AliasKey:
    tenant_id: str
    source_system: str
    source_animal_id: str

    def to_tuple(self) -> Tuple[str, str, str]:
        return (self.tenant_id, self.source_system, self.source_animal_id)


class MasterIdStore:
    """File-backed store for master animal identity resolution (Target).

    This store is deliberately storage-agnostic: it's just CSV + JSONL under a given directory.
    All changes MUST be recorded via identity_events.jsonl (audit trail).
    """

    def __init__(self, store_dir: Path):
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)

        self.master_csv = self.store_dir / "master_animals.csv"
        self.map_csv = self.store_dir / "animal_id_map.csv"
        self.events_jsonl = self.store_dir / "identity_events.jsonl"

        self._ensure_files()

    def _ensure_files(self) -> None:
        if not self.master_csv.exists():
            pd.DataFrame(
                columns=[
                    "tenant_id",
                    "master_animal_id",
                    "sex",
                    "sex_source",
                    "birth_date",
                    "birth_date_source",
                    "breed",
                    "breed_source",
                    "ear_tag_id",
                    "ear_tag_id_source",
                    "farm_id",
                    "farm_id_source",
                    "dam_animal_id",
                    "dam_animal_id_source",
                    "status",
                    "status_source",
                    "created_at",
                    "updated_at",
                ]
            ).to_csv(self.master_csv, index=False)
        if not self.map_csv.exists():
            pd.DataFrame(
                columns=[
                    "tenant_id",
                    "source_system",
                    "source_animal_id",
                    "master_animal_id",
                    "confidence",
                    "is_active",
                    "created_at",
                    "updated_at",
                ]
            ).to_csv(self.map_csv, index=False)
        if not self.events_jsonl.exists():
            self.events_jsonl.write_text("", encoding="utf-8")

    def read_master_df(self) -> pd.DataFrame:
        return pd.read_csv(self.master_csv, dtype=str).fillna("")

    def read_map_df(self) -> pd.DataFrame:
        return pd.read_csv(self.map_csv, dtype=str).fillna("")

    def write_master_df(self, df: pd.DataFrame) -> None:
        df.to_csv(self.master_csv, index=False)

    def write_map_df(self, df: pd.DataFrame) -> None:
        df.to_csv(self.map_csv, index=False)

    def append_event(self, event: Dict[str, Any]) -> None:
        # Append-only audit trail
        with self.events_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def find_master_by_alias(self, key: AliasKey) -> Optional[str]:
        df = self.read_map_df()
        m = df[
            (df["tenant_id"] == key.tenant_id)
            & (df["source_system"] == key.source_system)
            & (df["source_animal_id"] == key.source_animal_id)
            & (df["is_active"].isin(["1", "true", "True", "YES", "yes", "y", "Y", ""]))
        ]
        if m.empty:
            return None
        # last write wins
        return str(m.iloc[-1]["master_animal_id"]) or None

    def find_master_by_attribute(
        self, tenant_id: str, field: str, value: str
    ) -> Optional[str]:
        if not value:
            return None
        df = self.read_master_df()
        m = df[(df["tenant_id"] == tenant_id) & (df[field] == value)]
        if m.empty:
            return None
        return str(m.iloc[-1]["master_animal_id"]) or None

    def get_master(self, tenant_id: str, master_animal_id: str) -> Optional[Dict[str, str]]:
        df = self.read_master_df()
        m = df[(df["tenant_id"] == tenant_id) & (df["master_animal_id"] == master_animal_id)]
        if m.empty:
            return None
        return {k: str(v) for k, v in m.iloc[-1].to_dict().items()}

    def upsert_master(self, record: Dict[str, str]) -> None:
        df = self.read_master_df()
        tenant_id = record["tenant_id"]
        master_id = record["master_animal_id"]
        df_other = df[~((df["tenant_id"] == tenant_id) & (df["master_animal_id"] == master_id))]
        df_one = pd.DataFrame([record])
        out = pd.concat([df_other, df_one], ignore_index=True)
        self.write_master_df(out)

    def upsert_alias(
        self,
        tenant_id: str,
        source_system: str,
        source_animal_id: str,
        master_animal_id: str,
        confidence: str = "1.0",
        is_active: str = "1",
    ) -> Tuple[bool, Optional[str]]:
        """Returns (ok, conflict_master_id_if_any)."""
        df = self.read_map_df()
        existing = df[
            (df["tenant_id"] == tenant_id)
            & (df["source_system"] == source_system)
            & (df["source_animal_id"] == source_animal_id)
            & (df["is_active"] == "1")
        ]
        if not existing.empty:
            ex_master = str(existing.iloc[-1]["master_animal_id"])
            if ex_master and ex_master != master_animal_id:
                return (False, ex_master)

        now = utc_ts()
        row = {
            "tenant_id": tenant_id,
            "source_system": source_system,
            "source_animal_id": source_animal_id,
            "master_animal_id": master_animal_id,
            "confidence": str(confidence),
            "is_active": str(is_active),
            "created_at": now,
            "updated_at": now,
        }
        out = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        self.write_map_df(out)
        return (True, None)

    def move_aliases(self, tenant_id: str, from_master: str, to_master: str) -> int:
        df = self.read_map_df()
        m = (df["tenant_id"] == tenant_id) & (df["master_animal_id"] == from_master) & (df["is_active"] == "1")
        cnt = int(m.sum())
        if cnt == 0:
            return 0
        now = utc_ts()
        df.loc[m, "master_animal_id"] = to_master
        df.loc[m, "updated_at"] = now
        self.write_map_df(df)
        return cnt

    def list_aliases_for_master(self, tenant_id: str, master_id: str) -> List[Dict[str, str]]:
        df = self.read_map_df()
        m = df[(df["tenant_id"] == tenant_id) & (df["master_animal_id"] == master_id) & (df["is_active"] == "1")]
        if m.empty:
            return []
        return [ {k: str(v) for k,v in row.items()} for row in m.to_dict(orient="records") ]

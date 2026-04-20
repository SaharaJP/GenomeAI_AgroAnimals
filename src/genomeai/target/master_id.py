from __future__ import annotations

import hashlib
import json
import os
import random
import string
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from core.common.time import utc_timestamp_compact

from .master_id_store import AliasKey, MasterIdStore, utc_ts


def _rand_suffix(n: int = 6) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))


def generate_master_animal_id(tenant_id: str, source_system: str, source_animal_id: str) -> str:
    # deterministic-ish but with suffix to avoid collisions
    h = hashlib.sha1(f"{tenant_id}|{source_system}|{source_animal_id}".encode("utf-8")).hexdigest()[:10]
    return f"MA_{h}_{_rand_suffix(4)}"


def parse_iso_date(v: str) -> Optional[date]:
    if not v:
        return None
    try:
        return datetime.strptime(v, "%Y-%m-%d").date()
    except Exception:
        return None


@dataclass
class Conflict:
    conflict_type: str
    severity: str  # WARN|ERROR
    field: str
    message: str
    incoming_value: str = ""
    master_value: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_type": self.conflict_type,
            "severity": self.severity,
            "field": self.field,
            "message": self.message,
            "incoming_value": self.incoming_value,
            "master_value": self.master_value,
        }


class TrustRules:
    def __init__(self, rules: Dict[str, Any]):
        self.rules = rules or {}
        self.default_rank = self.rules.get("default_source_rank", [])
        self.field_rank = self.rules.get("field_source_rank", {})
        self.thresholds = self.rules.get("thresholds", {})

    @staticmethod
    def load(path: Path) -> "TrustRules":
        d = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return TrustRules(d)

    def rank_for_field(self, field: str) -> List[str]:
        return self.field_rank.get(field, self.default_rank)

    def more_trusted(self, field: str, src_new: str, src_old: str) -> bool:
        if not src_new:
            return False
        if not src_old:
            return True
        rank = self.rank_for_field(field)
        if src_new not in rank and src_old not in rank:
            return False
        if src_new in rank and src_old not in rank:
            return True
        if src_old in rank and src_new not in rank:
            return False
        return rank.index(src_new) < rank.index(src_old)

    def birth_date_max_delta_days(self) -> int:
        return int(self.thresholds.get("birth_date_max_delta_days", 30))

    def min_calving_age_days(self) -> int:
        return int(self.thresholds.get("min_calving_age_days", 450))


def _now_run_id(prefix: str = "id") -> str:
    return f"{prefix}_{utc_timestamp_compact()}_{_rand_suffix(6)}"



def new_identity_run_id() -> str:
    """Generate a run_id for identity operations."""
    return _now_run_id(prefix="id")

def identity_run_dir(artifacts_dir: Path, data_version: str, run_id: str) -> Path:
    # Target layout: artifacts/<data_version>/runs/<run_id>/identity/
    return Path(artifacts_dir) / data_version / "runs" / run_id / "identity"


class MasterIdService:
    """Master ID resolution + merge/split with mandatory audit trail."""

    def __init__(self, store: MasterIdStore, rules: TrustRules):
        self.store = store
        self.rules = rules

    def resolve(
        self,
        tenant_id: str,
        source_system: str,
        source_animal_id: str,
        attrs: Dict[str, str],
        actor: str = "system",
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        key = AliasKey(tenant_id=tenant_id, source_system=source_system, source_animal_id=source_animal_id)
        existing_master = self.store.find_master_by_alias(key)

        # Dedup heuristic: if alias unknown, but ear_tag_id matches existing master -> attach
        dedup_master = None
        if not existing_master:
            dedup_master = self.store.find_master_by_attribute(tenant_id, "ear_tag_id", attrs.get("ear_tag_id", ""))

        master_id = existing_master or dedup_master
        created = False

        before_master = None
        if master_id:
            before_master = self.store.get_master(tenant_id, master_id)

        conflicts: List[Conflict] = []
        if master_id and before_master:
            conflicts = detect_conflicts(before_master, attrs, self.rules)

        if not master_id:
            master_id = generate_master_animal_id(tenant_id, source_system, source_animal_id)
            created = True

        # upsert alias (may conflict)
        ok, conflict_master = self.store.upsert_alias(
            tenant_id=tenant_id,
            source_system=source_system,
            source_animal_id=source_animal_id,
            master_animal_id=master_id,
            confidence="1.0",
            is_active="1",
        )
        if not ok:
            conflicts.append(
                Conflict(
                    conflict_type="ALIAS_ALREADY_MAPPED",
                    severity="ERROR",
                    field="source_animal_id",
                    message=f"Alias already mapped to a different master_animal_id={conflict_master}",
                    incoming_value=master_id,
                    master_value=str(conflict_master or ""),
                )
            )

        # compute new master record
        after_master = self._apply_attrs_with_trust(
            tenant_id=tenant_id,
            master_animal_id=master_id,
            existing=before_master,
            incoming=attrs,
            source_system=source_system,
        )
        self.store.upsert_master(after_master)

        event = {
            "event_id": f"evt_{_rand_suffix(10)}",
            "event_ts": utc_ts(),
            "event_type": "RESOLVE",
            "tenant_id": tenant_id,
            "actor": actor,
            "run_id": run_id or "",
            "source_system": source_system,
            "source_animal_id": source_animal_id,
            "master_animal_id": master_id,
            "created_new_master": created,
            "dedup_by_ear_tag": bool(dedup_master and not existing_master),
            "conflicts": [c.to_dict() for c in conflicts],
            "before_master": before_master or {},
            "after_master": after_master,
        }
        self.store.append_event(event)

        return {
            "master_animal_id": master_id,
            "created": created,
            "conflicts": [c.to_dict() for c in conflicts],
        }

    def merge(
        self,
        tenant_id: str,
        from_master: str,
        into_master: str,
        actor: str,
        reason: str,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if from_master == into_master:
            raise ValueError("from_master equals into_master")

        before_from = self.store.get_master(tenant_id, from_master)
        before_into = self.store.get_master(tenant_id, into_master)
        if not before_from or not before_into:
            raise ValueError("master not found")

        moved = self.store.move_aliases(tenant_id, from_master, into_master)

        # mark from_master status
        after_from = dict(before_from)
        after_from["status"] = "merged"
        after_from["status_source"] = "system"
        after_from["updated_at"] = utc_ts()
        self.store.upsert_master(after_from)

        after_into = dict(before_into)
        after_into["updated_at"] = utc_ts()
        self.store.upsert_master(after_into)

        event = {
            "event_id": f"evt_{_rand_suffix(10)}",
            "event_ts": utc_ts(),
            "event_type": "MERGE",
            "tenant_id": tenant_id,
            "actor": actor,
            "run_id": run_id or "",
            "from_master_animal_id": from_master,
            "into_master_animal_id": into_master,
            "reason": reason,
            "moved_aliases": moved,
            "before_from": before_from,
            "before_into": before_into,
            "after_from": after_from,
            "after_into": after_into,
        }
        self.store.append_event(event)
        return {"moved_aliases": moved}

    def split(
        self,
        tenant_id: str,
        master_id: str,
        move_aliases: List[Tuple[str, str]],
        actor: str,
        reason: str,
        new_master_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        before_master = self.store.get_master(tenant_id, master_id)
        if not before_master:
            raise ValueError("master not found")

        if not move_aliases:
            raise ValueError("move_aliases is empty")

        new_id = new_master_id or f"MA_split_{_rand_suffix(8)}"
        # create new master from old snapshot but with updated timestamps
        after_new = dict(before_master)
        after_new["master_animal_id"] = new_id
        after_new["created_at"] = utc_ts()
        after_new["updated_at"] = utc_ts()
        self.store.upsert_master(after_new)

        # move selected aliases by rewriting map rows (append-only would be better; this is MVP)
        map_df = self.store.read_map_df()
        moved = 0
        for src_sys, src_id in move_aliases:
            m = (
                (map_df["tenant_id"] == tenant_id)
                & (map_df["source_system"] == src_sys)
                & (map_df["source_animal_id"] == src_id)
                & (map_df["is_active"] == "1")
                & (map_df["master_animal_id"] == master_id)
            )
            if m.any():
                map_df.loc[m, "master_animal_id"] = new_id
                map_df.loc[m, "updated_at"] = utc_ts()
                moved += int(m.sum())
        self.store.write_map_df(map_df)

        after_master = dict(before_master)
        after_master["updated_at"] = utc_ts()
        self.store.upsert_master(after_master)

        event = {
            "event_id": f"evt_{_rand_suffix(10)}",
            "event_ts": utc_ts(),
            "event_type": "SPLIT",
            "tenant_id": tenant_id,
            "actor": actor,
            "run_id": run_id or "",
            "from_master_animal_id": master_id,
            "new_master_animal_id": new_id,
            "reason": reason,
            "moved_aliases": [{"source_system": a, "source_animal_id": b} for a, b in move_aliases],
            "before_master": before_master,
            "after_master": after_master,
            "after_new": after_new,
        }
        self.store.append_event(event)
        return {"new_master_animal_id": new_id, "moved_aliases": moved}

    def _apply_attrs_with_trust(
        self,
        tenant_id: str,
        master_animal_id: str,
        existing: Optional[Dict[str, str]],
        incoming: Dict[str, str],
        source_system: str,
    ) -> Dict[str, str]:
        now = utc_ts()
        base = existing or {
            "tenant_id": tenant_id,
            "master_animal_id": master_animal_id,
            "sex": "",
            "sex_source": "",
            "birth_date": "",
            "birth_date_source": "",
            "breed": "",
            "breed_source": "",
            "ear_tag_id": "",
            "ear_tag_id_source": "",
            "farm_id": "",
            "farm_id_source": "",
            "dam_animal_id": "",
            "dam_animal_id_source": "",
            "status": "active",
            "status_source": "system",
            "created_at": now,
            "updated_at": now,
        }
        base["updated_at"] = now

        for field, source_field in [
            ("sex", "sex_source"),
            ("birth_date", "birth_date_source"),
            ("breed", "breed_source"),
            ("ear_tag_id", "ear_tag_id_source"),
            ("farm_id", "farm_id_source"),
            ("dam_animal_id", "dam_animal_id_source"),
            ("status", "status_source"),
        ]:
            v_new = (incoming.get(field) or "").strip()
            if not v_new:
                continue
            v_old = (base.get(field) or "").strip()
            src_old = (base.get(source_field) or "").strip()
            if (not v_old) or (v_new == v_old) or self.rules.more_trusted(field, source_system, src_old):
                base[field] = v_new
                base[source_field] = source_system if v_new else src_old

        return base


def detect_conflicts(master: Dict[str, str], incoming: Dict[str, str], rules: TrustRules) -> List[Conflict]:
    out: List[Conflict] = []

    def _m(field: str) -> str:
        return (master.get(field) or "").strip()

    def _i(field: str) -> str:
        return (incoming.get(field) or "").strip()

    # 1) sex mismatch
    if _m("sex") and _i("sex") and _m("sex") != _i("sex"):
        out.append(Conflict("SEX_MISMATCH", "ERROR", "sex", "Incoming sex conflicts with master", _i("sex"), _m("sex")))

    # 2) birth_date mismatch > threshold
    bd_m = parse_iso_date(_m("birth_date"))
    bd_i = parse_iso_date(_i("birth_date"))
    if bd_m and bd_i:
        delta = abs((bd_m - bd_i).days)
        if delta > rules.birth_date_max_delta_days():
            out.append(
                Conflict(
                    "BIRTH_DATE_MISMATCH",
                    "ERROR",
                    "birth_date",
                    f"Birth dates differ by {delta} days (>{rules.birth_date_max_delta_days()})",
                    _i("birth_date"),
                    _m("birth_date"),
                )
            )

    # 3) breed mismatch
    if _m("breed") and _i("breed") and _m("breed") != _i("breed"):
        out.append(Conflict("BREED_MISMATCH", "WARN", "breed", "Incoming breed differs from master", _i("breed"), _m("breed")))

    # 4) farm mismatch
    if _m("farm_id") and _i("farm_id") and _m("farm_id") != _i("farm_id"):
        out.append(Conflict("FARM_MISMATCH", "WARN", "farm_id", "Incoming farm differs from master", _i("farm_id"), _m("farm_id")))

    # 5) ear tag mismatch
    if _m("ear_tag_id") and _i("ear_tag_id") and _m("ear_tag_id") != _i("ear_tag_id"):
        out.append(Conflict("EAR_TAG_MISMATCH", "ERROR", "ear_tag_id", "Incoming ear_tag differs from master", _i("ear_tag_id"), _m("ear_tag_id")))

    # 6) dam mismatch
    if _m("dam_animal_id") and _i("dam_animal_id") and _m("dam_animal_id") != _i("dam_animal_id"):
        out.append(Conflict("DAM_MISMATCH", "WARN", "dam_animal_id", "Incoming dam differs from master", _i("dam_animal_id"), _m("dam_animal_id")))

    # 7) status conflict
    if _m("status") and _i("status") and _m("status") != _i("status"):
        out.append(Conflict("STATUS_CONFLICT", "WARN", "status", "Incoming status differs from master", _i("status"), _m("status")))

    # 8) invalid sex value
    if _i("sex") and _i("sex") not in {"F", "M", "U"}:
        out.append(Conflict("SEX_INVALID_VALUE", "ERROR", "sex", "Sex must be F|M|U", _i("sex"), _m("sex")))

    # 9) invalid birth_date format
    if _i("birth_date") and not parse_iso_date(_i("birth_date")):
        out.append(Conflict("BIRTH_DATE_INVALID_FORMAT", "ERROR", "birth_date", "birth_date must be YYYY-MM-DD", _i("birth_date"), _m("birth_date")))

    # 10) calving date earlier than birth date (if provided in incoming)
    cd_i = parse_iso_date(_i("calving_date"))
    if bd_i and cd_i and cd_i <= bd_i:
        out.append(Conflict("CALVING_BEFORE_BIRTH", "ERROR", "calving_date", "calving_date must be after birth_date", _i("calving_date"), _m("birth_date")))

    # 11) unrealistic calving age (if provided)
    if bd_i and cd_i:
        age_days = (cd_i - bd_i).days
        if age_days < rules.min_calving_age_days():
            out.append(Conflict("CALVING_AGE_TOO_LOW", "WARN", "calving_date", f"Age at calving too low ({age_days}d)", str(age_days), ""))

    # 12) missing mandatory identity fields for certain sources (example)
    if incoming.get("required_by_source") == "lab" and not _i("ear_tag_id"):
        out.append(Conflict("LAB_MISSING_EAR_TAG", "ERROR", "ear_tag_id", "Lab source must provide ear_tag_id", "", _m("ear_tag_id")))

    return out

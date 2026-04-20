from pathlib import Path

import pytest

from genomeai.target.master_id import MasterIdService, TrustRules, detect_conflicts
from genomeai.target.master_id_store import MasterIdStore, AliasKey


def test_detect_conflicts_has_many_types(tmp_path: Path):
    rules = TrustRules.load(Path(__file__).resolve().parents[2] / "configs" / "target" / "trust_rules.yaml")

    master = {
        "tenant_id": "default",
        "master_animal_id": "MA_X",
        "sex": "F",
        "birth_date": "2020-01-01",
        "breed": "HO",
        "ear_tag_id": "ET1",
        "farm_id": "FARM_1",
        "dam_animal_id": "DAM_1",
        "status": "active",
    }

    # Call 1: trigger mismatches + calving checks
    incoming1 = {
        "sex": "M",
        "birth_date": "2018-01-01",
        "breed": "BS",
        "ear_tag_id": "ET2",
        "farm_id": "FARM_2",
        "dam_animal_id": "DAM_2",
        "status": "culled",
        "calving_date": "2017-01-01",  # before birth
    }
    c1 = detect_conflicts(master, incoming1, rules)

    # Call 2: invalid formats + missing per-source requirement
    incoming2 = {
        "sex": "X",  # invalid
        "birth_date": "2018/01/01",  # invalid format
        "required_by_source": "lab",  # lab requires ear_tag_id in our rules
    }
    c2 = detect_conflicts(master, incoming2, rules)

    types = {c["conflict_type"] if isinstance(c, dict) else c.conflict_type for c in [*c1, *c2]}
    # minimum 10 conflict types (Target requirement)
    assert len(types) >= 10


def test_master_id_resolve_merge_split_audited(tmp_path: Path):
    store = MasterIdStore(tmp_path)
    rules = TrustRules.load(Path(__file__).resolve().parents[2] / "configs" / "target" / "trust_rules.yaml")
    svc = MasterIdService(store, rules)

    # resolve two different aliases -> two masters
    r1 = svc.resolve("default", "registry", "A1001", {"sex": "F", "ear_tag_id": "ET123", "birth_date": "2022-03-01"}, actor="u1", run_id="id_test")
    r2 = svc.resolve("default", "registry", "A2001", {"sex": "M", "ear_tag_id": "ET999", "birth_date": "2021-02-01"}, actor="u1", run_id="id_test")
    assert r1["master_animal_id"] != r2["master_animal_id"]

    # merge master2 into master1
    svc.merge("default", from_master=r2["master_animal_id"], into_master=r1["master_animal_id"], actor="admin", reason="duplicate", run_id="id_test")

    # mapping for A2001 should now point to master1
    m = store.find_master_by_alias(AliasKey(tenant_id="default", source_system="registry", source_animal_id="A2001"))
    assert m == r1["master_animal_id"]

    # split: move A2001 into a new master
    svc.split(
        "default",
        master_id=r1["master_animal_id"],
        move_aliases=[("registry", "A2001")],
        actor="admin",
        reason="wrong merge",
        run_id="id_test",
    )

    # events log should have at least 4 lines: resolve, resolve, merge, split
    events = (tmp_path / "identity_events.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(events) >= 4

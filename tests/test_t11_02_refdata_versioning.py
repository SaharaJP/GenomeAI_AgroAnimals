from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from genomeai.refdata import RefdataStore
from genomeai.economics_v2 import run_economics_v2


def _make_web_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    from web_cabinet.db import init_db

    init_db(conn)
    return conn


def test_refdata_versions_create_activate_rollback(tmp_path: Path) -> None:
    db_path = tmp_path / "web.db"
    conn = _make_web_db(db_path)
    try:
        # create a user for created_by_username enrichment
        conn.execute(
            "INSERT INTO users_v2(tenant_id, username, password_hash, role, is_active, created_at) VALUES(?,?,?,?,?,?)",
            ("default", "admin", "x", "Admin", 1, "2025-01-01T00:00:00Z"),
        )
        user_id = int(conn.execute("SELECT id FROM users_v2 WHERE tenant_id='default' AND username='admin'").fetchone()[0])
        conn.commit()

        store = RefdataStore(conn)
        store.ensure()

        # v1
        v1 = store.create_price_version_from_items(
            tenant_id="default",
            effective_date="2025-01-01",
            created_by=user_id,
            created_by_username="admin",
            comment="v1",
            items=[
                {"item_type": "milk", "item_code": "price_per_kg", "unit": "kg", "currency": "RUB", "value": 50},
                {"item_type": "feed", "item_code": "cost_per_kg_dm", "unit": "kgDM", "currency": "RUB", "value": 30},
            ],
        )
        assert v1.get("version_id")
        store.set_active_version(tenant_id="default", kind="price_book", version_id=str(v1["version_id"]))
        assert store.get_active_version(tenant_id="default", kind="price_book") == str(v1["version_id"])

        # v2 (override milk)
        v2 = store.create_price_version_from_items(
            tenant_id="default",
            effective_date="2025-02-01",
            created_by=user_id,
            comment="v2",
            base_version_id=str(v1["version_id"]),
            items=[
                # also accept meta_json-formatted item coming from list/get operations
                {"item_type": "milk", "item_code": "price_per_kg", "unit": "kg", "currency": "RUB", "value": 60, "meta_json": "{}"},
            ],
        )
        store.set_active_version(tenant_id="default", kind="price_book", version_id=str(v2["version_id"]))
        assert store.get_active_version(tenant_id="default", kind="price_book") == str(v2["version_id"])

        # list includes status + created_by_username
        vers = store.list_price_versions(tenant_id="default", limit=10)
        assert any(x.get("status") == "active" for x in vers)
        assert any(str(x.get("created_by_username") or "") == "admin" for x in vers)

        # rollback
        store.set_active_version(tenant_id="default", kind="price_book", version_id=str(v1["version_id"]))
        assert store.get_active_version(tenant_id="default", kind="price_book") == str(v1["version_id"])

        # assumptions
        a1 = store.create_assumptions_version_from_items(
            tenant_id="default",
            effective_date="2025-01-01",
            created_by=user_id,
            comment="a1",
            items=[
                {"key": "economics.vet_cost_per_treatment_event_rub", "value": 1500, "unit": "RUB", "note": "default"},
                {"key": "economics.repro.insemination_cost_rub", "value": 800, "unit": "RUB"},
            ],
        )
        store.set_active_version(tenant_id="default", kind="assumptions", version_id=str(a1["version_id"]))
        d = store.load_assumptions_as_dict(tenant_id="default", version_id=str(a1["version_id"]))
        assert float(d["economics.vet_cost_per_treatment_event_rub"]) == pytest.approx(1500.0)

    finally:
        conn.close()


def test_economics_v2_uses_refdata_price_book_version(tmp_path: Path) -> None:
    """Economics v2 must be reproducible against a chosen price_book version."""

    repo_root = Path(__file__).resolve().parents[1]
    fixtures = repo_root / "data" / "fixtures" / "target_v2"
    assert fixtures.exists()

    # Build a web.db with a single price book version
    db_path = tmp_path / "web.db"
    conn = _make_web_db(db_path)
    try:
        conn.execute(
            "INSERT INTO users_v2(tenant_id, username, password_hash, role, is_active, created_at) VALUES(?,?,?,?,?,?)",
            ("default", "admin", "x", "Admin", 1, "2025-01-01T00:00:00Z"),
        )
        user_id = int(conn.execute("SELECT id FROM users_v2 WHERE tenant_id='default' AND username='admin'").fetchone()[0])
        conn.commit()

        store = RefdataStore(conn)
        store.ensure()
        v = store.create_price_version_from_items(
            tenant_id="default",
            effective_date="2025-01-01",
            created_by=user_id,
            comment="override",
            items=[
                {"item_type": "milk", "item_code": "price_per_kg", "unit": "kg", "currency": "RUB", "value": 60},
                {"item_type": "feed", "item_code": "cost_per_kg_dm", "unit": "kgDM", "currency": "RUB", "value": 10},
                {"item_type": "other", "item_code": "cost_per_farm_day", "unit": "farm_day", "currency": "RUB", "value": 0},
            ],
        )
        store.set_active_version(tenant_id="default", kind="price_book", version_id=str(v["version_id"]))
        conn.commit()

    finally:
        conn.close()

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    res = run_economics_v2(
        artifacts_root=artifacts,
        data_version="dv_test",
        date_from="2025-01-05",
        date_to="2025-01-05",
        cfg_path=repo_root / "configs" / "economics" / "economics_v2.yaml",
        input_dir=fixtures,
        tenant_id="default",
        refdata_db_path=db_path,
        price_version=str(v["version_id"]),
    )
    assert res.get("ok") is True

    run_id = str(res.get("economics_run"))
    run_dir = artifacts / "dv_test" / "economics_v2" / run_id
    assert (run_dir / "manifest.json").exists()

    import json
    import pandas as pd

    mf = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert mf["versions"]["price_book_version"] == str(v["version_id"])

    df = pd.read_csv(run_dir / "economics_daily.csv")
    farm = df[(df["level"] == "farm") & (df["date"] == "2025-01-05")]
    assert len(farm) == 1
    row = farm.iloc[0]

    # milk_kg=32.4 (fixtures), price override 60 RUB/kg => revenue 1944
    assert float(row["revenue_milk_rub"]) == pytest.approx(1944.0, abs=1e-6)
    # feed: 3500 as-fed, dm_pct=52% => 1820 DM, cost 10 => 18200
    assert float(row["cost_feed_rub"]) == pytest.approx(18200.0, abs=1e-6)
    # other forced to 0
    assert float(row["cost_other_rub"]) == pytest.approx(0.0, abs=1e-6)

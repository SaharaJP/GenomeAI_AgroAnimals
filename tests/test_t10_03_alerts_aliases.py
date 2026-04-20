from __future__ import annotations

import sqlite3

from web_cabinet.db import init_db
from web_cabinet.alerts_v2 import AlertCreate, create_alert, list_alerts_for_object


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def test_list_alerts_for_object_includes_group_aliases() -> None:
    with _conn() as conn:
        a1 = AlertCreate(
            alert_type="TEST.GROUP",
            title="t1",
            source="unit",
            cause="c",
            confidence=None,
            deadline=None,
            owner_user_id=None,
            attachments=[],
            why={},
            what_to_do=[],
            object_type="group",
            object_id="P1",
            data_version="dv_demo",
        )
        a2 = AlertCreate(
            alert_type="TEST.PEN",
            title="t2",
            source="unit",
            cause="c",
            confidence=None,
            deadline=None,
            owner_user_id=None,
            attachments=[],
            why={},
            what_to_do=[],
            object_type="pen",
            object_id="P1",
            data_version="dv_demo",
        )
        create_alert(conn, tenant_id="default", a=a1)
        create_alert(conn, tenant_id="default", a=a2)

        res = list_alerts_for_object(conn, tenant_id="default", object_type="group", object_id="P1", include_aliases=True)
        ids = {x.get("alert_type") for x in (res.get("alerts") or [])}
        assert "TEST.GROUP" in ids
        assert "TEST.PEN" in ids


def test_list_alerts_for_object_includes_animal_aliases() -> None:
    with _conn() as conn:
        a1 = AlertCreate(
            alert_type="TEST.ANIMAL",
            title="t1",
            source="unit",
            cause="c",
            confidence=None,
            deadline=None,
            owner_user_id=None,
            attachments=[],
            why={},
            what_to_do=[],
            object_type="animal",
            object_id="A1",
            data_version="dv_demo",
        )
        a2 = AlertCreate(
            alert_type="TEST.COW",
            title="t2",
            source="unit",
            cause="c",
            confidence=None,
            deadline=None,
            owner_user_id=None,
            attachments=[],
            why={},
            what_to_do=[],
            object_type="cow",
            object_id="A1",
            data_version="dv_demo",
        )
        create_alert(conn, tenant_id="default", a=a1)
        create_alert(conn, tenant_id="default", a=a2)

        res = list_alerts_for_object(conn, tenant_id="default", object_type="animal", object_id="A1", include_aliases=True)
        ids = {x.get("alert_type") for x in (res.get("alerts") or [])}
        assert "TEST.ANIMAL" in ids
        assert "TEST.COW" in ids

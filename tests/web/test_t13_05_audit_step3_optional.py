from __future__ import annotations

import importlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[2]
    storage = tmp_path / "web_storage"
    artifacts = tmp_path / "artifacts"
    os.environ["GENOMEAI_PROJECT_ROOT"] = str(repo_root)
    os.environ["GENOMEAI_WEB_STORAGE"] = str(storage)
    os.environ["GENOMEAI_ARTIFACTS_ROOT"] = str(artifacts)
    os.environ["GENOMEAI_WEB_DISABLE_WORKER"] = "1"
    os.environ["GENOMEAI_WEB_SECRET"] = "test-secret"

    import web_cabinet.app as appmod

    importlib.reload(appmod)
    with TestClient(appmod.app) as c:
        yield c


def _login(c: TestClient, username: str = "admin", password: str = "admin"):
    r = c.post("/login", data={"username": username, "password": password}, follow_redirects=False)
    assert r.status_code in (302, 303), r.text


def _seed_audit_rows(rows: list[dict]):
    import web_cabinet.app as appmod
    from web_cabinet.audit import AUDIT_SCHEMA_VERSION, _canonical_action_group, _object_ref
    from web_cabinet.db import connect

    conn = connect(appmod.settings.db_path)
    try:
        for row in rows:
            action = row["action"]
            object_type = row.get("object_type")
            object_id = row.get("object_id")
            conn.execute(
                """
                INSERT INTO audit_log(
                  ts, tenant_id, user_id, username, role,
                  action, action_group, object_type, object_id, object_ref,
                  data_version, run_id, before_json, after_json,
                  ip, user_agent, status, error, request_id, schema_version,
                  archived_at, archive_reason, archive_batch_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    row["ts"],
                    "default",
                    1,
                    row.get("username", "admin"),
                    row.get("role", "Admin"),
                    action,
                    row.get("action_group") or _canonical_action_group(action),
                    object_type,
                    object_id,
                    _object_ref(object_type, object_id),
                    row.get("data_version"),
                    row.get("run_id"),
                    row.get("before_json"),
                    row.get("after_json"),
                    None,
                    None,
                    row.get("status", "OK"),
                    None,
                    None,
                    AUDIT_SCHEMA_VERSION,
                    row.get("archived_at"),
                    row.get("archive_reason"),
                    row.get("archive_batch_id"),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def test_t13_05_audit_facets_api_returns_group_status_action_and_user_counts(client: TestClient):
    _login(client)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    marker = "FACET_MARK_001"
    _seed_audit_rows(
        [
            {"ts": (now - timedelta(minutes=3)).isoformat(), "action": "pipeline.enqueue", "object_type": "job", "object_id": f"{marker}_RUN_A", "run_id": "run_a"},
            {"ts": (now - timedelta(minutes=2)).isoformat(), "action": "pipeline.enqueue", "object_type": "job", "object_id": f"{marker}_RUN_B", "run_id": "run_b"},
            {"ts": (now - timedelta(minutes=1)).isoformat(), "action": "export.download", "object_type": "file", "object_id": f"{marker}_EXPORT", "username": "director", "role": "Director"},
        ]
    )

    r = client.get("/api/audit/facets", params={"q": marker, "scope": "active", "limit": 200})
    assert r.status_code == 200, r.text
    facets = r.json()["facets"]
    assert facets["summary"]["filtered_total"] == 3
    assert any(item["key"] == "run" and item["count"] == 2 for item in facets["by_action_group"])
    assert any(item["key"] == "export" and item["count"] == 1 for item in facets["by_action_group"])
    assert any(item["key"] == "OK" and item["count"] == 3 for item in facets["by_status"])
    assert facets["top_actions"][0]["key"] == "pipeline.enqueue"
    assert facets["top_actions"][0]["count"] == 2
    assert any(item["key"] == "admin" and item["count"] == 2 for item in facets["top_users"])
    assert any(item["key"] == "director" and item["count"] == 1 for item in facets["top_users"])


def test_t13_05_audit_retention_archives_old_rows_and_keeps_recent_active(client: TestClient):
    _login(client)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    _seed_audit_rows(
        [
            {"ts": (now - timedelta(days=120)).isoformat(), "action": "pipeline.enqueue", "object_type": "job", "object_id": "ARCHIVE_OLD_001", "run_id": "run_old_001"},
            {"ts": (now - timedelta(days=10)).isoformat(), "action": "pipeline.enqueue", "object_type": "job", "object_id": "ARCHIVE_NEW_001", "run_id": "run_new_001"},
        ]
    )

    dry_run = client.post("/api/audit/archive-old", data={"dry_run": "1", "limit": "10"})
    assert dry_run.status_code == 200, dry_run.text
    assert dry_run.json()["dry_run"] is True
    assert dry_run.json()["candidates"] >= 1

    apply_resp = client.post("/api/audit/archive-old", data={"dry_run": "0", "limit": "10"})
    assert apply_resp.status_code == 200, apply_resp.text
    payload = apply_resp.json()
    assert payload["ok"] is True
    assert payload["result"]["rows_archived"] >= 1

    active_old = client.get("/api/audit", params={"object_id": "ARCHIVE_OLD_001", "limit": 50})
    assert active_old.status_code == 200, active_old.text
    assert active_old.json()["rows"] == []

    archived_old = client.get("/api/audit", params={"object_id": "ARCHIVE_OLD_001", "scope": "archived", "limit": 50})
    assert archived_old.status_code == 200, archived_old.text
    archived_rows = archived_old.json()["rows"]
    assert archived_rows
    assert archived_rows[0]["archived_at"]
    assert archived_rows[0]["archive_reason"] == "retention_policy"

    active_new = client.get("/api/audit", params={"object_id": "ARCHIVE_NEW_001", "scope": "active", "limit": 50})
    assert active_new.status_code == 200, active_new.text
    assert active_new.json()["rows"]
    assert active_new.json()["rows"][0]["archived_at"] is None

    audit_apply = client.get("/api/audit", params={"action": "config.audit_retention.apply", "scope": "active", "limit": 50})
    assert audit_apply.status_code == 200, audit_apply.text
    rows = audit_apply.json()["rows"]
    assert rows
    assert rows[0]["action_group"] == "config"
    assert rows[0]["after"]["rows_archived"] >= 1

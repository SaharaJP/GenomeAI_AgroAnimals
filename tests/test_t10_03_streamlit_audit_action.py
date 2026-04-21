from __future__ import annotations

import sqlite3
from pathlib import Path


def test_streamlit_audit_action_writes_rows(tmp_path: Path):
    """T10-03: critical UI actions must be audited (append-only)."""

    from streamlit_app.common import Context, audit_action

    ctx = Context(
        artifacts_dir=tmp_path / "artifacts",
        web_storage_dir=tmp_path / "web_storage",
    )
    ctx.artifacts_dir.mkdir(parents=True, exist_ok=True)
    ctx.web_storage_dir.mkdir(parents=True, exist_ok=True)

    user = {
        "tenant_id": "default",
        "id": 1,
        "username": "tester",
        "role": "Admin",
    }

    actions = ["drilldown.open", "report.open", "tasks.create", "decision.append"]
    for a in actions:
        audit_action(
            ctx,
            user,
            action=a,
            object_type="animal",
            object_id="A-1",
            data_version="dv_test",
            run_id="run_test",
            after={"k": a},
        )

    db_path = ctx.web_storage_dir / "web.db"
    assert db_path.exists()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT action FROM audit_log WHERE tenant_id=? ORDER BY id DESC LIMIT 50",
            ("default",),
        ).fetchall()
    finally:
        conn.close()

    got = [r["action"] for r in rows]
    for a in actions:
        assert a in got

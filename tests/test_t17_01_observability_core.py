from __future__ import annotations

import io
import json
import sqlite3

from core.audit.events import write_audit
from core.observability import configure_structured_logging, correlation_scope, log_event
from core.infra.web_db import init_db


def test_t17_01_structured_log_payload_includes_correlation_fields() -> None:
    stream = io.StringIO()
    logger = configure_structured_logging(force=True, stream=stream)
    with correlation_scope(request_id="REQ-T17", run_id="run_t17", data_version="dv_t17", component="tests"):
        payload = log_event("test.observability", logger=logger, user_id=42)

    assert payload["request_id"] == "REQ-T17"
    assert payload["run_id"] == "run_t17"
    assert payload["data_version"] == "dv_t17"
    assert payload["user_id"] == 42
    rendered = stream.getvalue().strip().splitlines()[-1]
    decoded = json.loads(rendered)
    assert decoded["event"] == "test.observability"
    assert decoded["request_id"] == "REQ-T17"
    assert decoded["component"] == "tests"


def test_t17_01_write_audit_uses_correlation_context_defaults() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    with correlation_scope(request_id="REQ-AUDIT", data_version="dv_audit", run_id="run_audit"):
        write_audit(
            conn,
            tenant_id="default",
            user_id=1,
            username="operator",
            role="operator",
            action="test.audit",
            status="OK",
        )

    row = conn.execute("SELECT request_id, data_version, run_id FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    assert row is not None
    assert row["request_id"] == "REQ-AUDIT"
    assert row["data_version"] == "dv_audit"
    assert row["run_id"] == "run_audit"

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from core.recovery import compare_selected_artifacts, compare_sqlite_tables, run_restore_drill
from genomeai.cli import main
from web_cabinet.db import connect, init_db


def _prepare_source_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    artifacts = tmp_path / "src" / "artifacts"
    web_storage = tmp_path / "src" / "web_storage"
    db_path = web_storage / "web.db"

    (artifacts / "dv_demo_001" / "canonical").mkdir(parents=True, exist_ok=True)
    (artifacts / "dv_demo_001" / "canonical" / "animals.csv").write_text("animal_id\nA001\n", encoding="utf-8")
    (artifacts / "dv_demo_001" / "reports").mkdir(parents=True, exist_ok=True)
    (artifacts / "dv_demo_001" / "reports" / "report_summary.json").write_text(json.dumps({"kpi": 1}, ensure_ascii=False), encoding="utf-8")
    (artifacts / "dv_demo_001" / "reports" / "fact_pack.json").write_text(json.dumps({"facts": [1, 2, 3]}, ensure_ascii=False), encoding="utf-8")
    (artifacts / "dv_demo_001" / "reports" / "manifest.json").write_text(json.dumps({"run_id": "run_demo_001"}, ensure_ascii=False), encoding="utf-8")

    (web_storage / "uploads").mkdir(parents=True, exist_ok=True)
    (web_storage / "logs").mkdir(parents=True, exist_ok=True)
    (web_storage / "config_overrides").mkdir(parents=True, exist_ok=True)
    (web_storage / "uploads" / "sample.txt").write_text("upload", encoding="utf-8")

    conn = connect(db_path)
    try:
        init_db(conn)
        conn.execute(
            "INSERT INTO jobs(public_job_id, queue_name, pipeline_key, kind, status, created_at, user, command, args_json, log_path, artifacts_json, result_json, tenant_id, user_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "job_demo_001",
                "default",
                "qc",
                "qc",
                "done",
                "2026-03-09T00:00:00+00:00",
                "operator",
                "python -m genomeai qc",
                json.dumps({"data_version": "dv_demo_001", "run_id": "run_demo_001"}),
                "logs/job_demo_001.log",
                "[]",
                "{}",
                "default",
                1,
            ),
        )
        conn.execute(
            "INSERT INTO decision_log_v2(decision_id, tenant_id, created_at, recommendation_id, action, user_id, username, object_type, object_id, data_version, metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                "decision_001",
                "default",
                "2026-03-09T00:00:00+00:00",
                "rec_001",
                "accept",
                1,
                "operator",
                "animal",
                "A001",
                "dv_demo_001",
                json.dumps({"reason": "ok"}, ensure_ascii=False),
            ),
        )
        conn.execute(
            "INSERT INTO tasks_v1(task_id, tenant_id, created_at, updated_at, task_type, title, priority, status, object_type, object_id, why_json, what_to_do_json, data_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "task_001",
                "default",
                "2026-03-09T00:00:00+00:00",
                "2026-03-09T00:00:00+00:00",
                "health",
                "Check A001",
                3,
                "open",
                "animal",
                "A001",
                json.dumps({"reason": "alert"}, ensure_ascii=False),
                json.dumps(["inspect"], ensure_ascii=False),
                "dv_demo_001",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return artifacts, web_storage, db_path


def test_t17_07_restore_drill_runs_backup_restore_verify_and_audits(tmp_path: Path) -> None:
    artifacts, web_storage, db_path = _prepare_source_tree(tmp_path)
    report_root = tmp_path / "reports"

    result = run_restore_drill(
        project_root=tmp_path,
        artifacts_root=artifacts,
        web_storage=web_storage,
        db_path=db_path,
        report_root=report_root,
    )

    assert result["summary"]["ok"] is True
    assert result["restore"]["ok"] is True
    assert result["artifact_compare"]["ok"] is True
    assert result["db_compare"]["ok"] is True
    assert Path(result["backup_zip"]).exists()
    assert Path(result["report_paths"]["json"]).exists()
    assert Path(result["report_paths"]["md"]).exists()
    assert result["restore_paths"]["kept"] is False
    assert not Path(result["restore_paths"]["artifacts_root"]).exists()

    conn = connect(db_path)
    try:
        rows = conn.execute("SELECT action, status FROM audit_log WHERE action='backup.drill' ORDER BY id DESC LIMIT 1").fetchall()
    finally:
        conn.close()
    assert rows
    assert rows[0][1] == "OK"


def test_t17_07_compare_selected_artifacts_reports_checksum_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source"
    restored = tmp_path / "restored"
    (source / "reports").mkdir(parents=True, exist_ok=True)
    (restored / "reports").mkdir(parents=True, exist_ok=True)
    (source / "reports" / "manifest.json").write_text('{"x":1}', encoding="utf-8")
    (restored / "reports" / "manifest.json").write_text('{"x":2}', encoding="utf-8")

    result = compare_selected_artifacts(
        source_root=source,
        restored_root=restored,
        patterns=["**/manifest.json"],
        max_examples=5,
    )

    assert result["ok"] is False
    assert result["mismatch_count"] == 1
    assert result["mismatches"][0]["reason"] == "checksum_mismatch"


def test_t17_07_compare_sqlite_tables_ignores_restore_audit_delta(tmp_path: Path) -> None:
    source_db = tmp_path / "source.db"
    restored_db = tmp_path / "restored.db"
    for db in [source_db, restored_db]:
        conn = sqlite3.connect(str(db))
        try:
            conn.execute("CREATE TABLE audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, status TEXT, ts TEXT)")
            conn.execute("INSERT INTO audit_log(action, status, ts) VALUES (?,?,?)", ("backup.create", "OK", "2026-03-09T00:00:00+00:00"))
            conn.commit()
        finally:
            conn.close()
    conn = sqlite3.connect(str(restored_db))
    try:
        conn.execute("INSERT INTO audit_log(action, status, ts) VALUES (?,?,?)", ("backup.restore", "OK", "2026-03-09T00:01:00+00:00"))
        conn.commit()
    finally:
        conn.close()

    result = compare_sqlite_tables(
        source_db=source_db,
        restored_db=restored_db,
        tables=["audit_log"],
        audit_ignore_actions=["backup.restore"],
        max_examples=5,
    )

    assert result["ok"] is True
    assert result["tables"]["audit_log"]["status"] == "ok"


def test_t17_07_cli_restore_drill_command(tmp_path: Path, capsys) -> None:
    artifacts, web_storage, db_path = _prepare_source_tree(tmp_path)
    rc = main(
        [
            "restore-drill",
            "--project-root",
            str(tmp_path),
            "--artifacts",
            str(artifacts),
            "--web-storage",
            str(web_storage),
            "--db-path",
            str(db_path),
            "--report-root",
            str(tmp_path / "reports_cli"),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    assert "RESTORE_DRILL_OK" in captured.out
    assert "artifact_mismatches=0" in captured.out
    assert "db_mismatches=0" in captured.out

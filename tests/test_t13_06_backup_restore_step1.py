from __future__ import annotations

import json
import zipfile
from pathlib import Path

from genomeai.backup_restore import BACKUP_FORMAT_V2, make_backup, restore_backup
from web_cabinet.db import connect, init_db


def _prepare_source_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    artifacts = tmp_path / "src" / "artifacts"
    web_storage = tmp_path / "src" / "web_storage"
    db_path = web_storage / "web.db"

    (artifacts / "dv_demo_001" / "canonical").mkdir(parents=True, exist_ok=True)
    (artifacts / "dv_demo_001" / "canonical" / "animals.csv").write_text("animal_id\nA001\n", encoding="utf-8")
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
                "{}",
                "logs/job_demo_001.log",
                "[]",
                "{}",
                "default",
                1,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return artifacts, web_storage, db_path


def test_t13_06_step1_backup_manifest_v2_includes_db_component_and_audit(tmp_path: Path):
    artifacts, web_storage, db_path = _prepare_source_tree(tmp_path)
    backup_zip = tmp_path / "backup.zip"

    res = make_backup(artifacts_root=artifacts, web_storage=web_storage, db_path=db_path, out_zip=backup_zip)

    assert backup_zip.exists()
    assert res.backup_id == "backup"

    with zipfile.ZipFile(backup_zip, "r") as zf:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        names = set(zf.namelist())

    assert manifest["format"] == BACKUP_FORMAT_V2
    assert "db" in manifest["components"]
    assert manifest["components"]["db"]["file_count"] >= 1
    assert "db/web.db" in names
    assert "web_storage/web.db" not in names
    assert any(e["component"] == "db" and e["path"] == "db/web.db" for e in manifest["entries"])
    assert "dv_demo_001" in manifest["data_versions"]

    conn = connect(db_path)
    try:
        rows = conn.execute("SELECT action FROM audit_log WHERE action='backup.create' ORDER BY id DESC LIMIT 5").fetchall()
    finally:
        conn.close()
    assert rows, "backup.create must be written to audit before snapshot"


def test_t13_06_step1_restore_verifies_checksums_runs_smoke_and_writes_restore_audit(tmp_path: Path):
    artifacts, web_storage, db_path = _prepare_source_tree(tmp_path)
    backup_zip = tmp_path / "backup.zip"
    _ = make_backup(artifacts_root=artifacts, web_storage=web_storage, db_path=db_path, out_zip=backup_zip)

    restore_artifacts = tmp_path / "restore" / "artifacts"
    restore_web = tmp_path / "restore" / "web_storage"
    restore_db = restore_web / "web.db"

    res = restore_backup(
        backup_zip=backup_zip,
        artifacts_root=restore_artifacts,
        web_storage=restore_web,
        db_path=restore_db,
        force=True,
        smoke_check=True,
    )

    assert res["ok"] is True
    assert res["verified_files"] == res["total_files"]
    assert res["smoke"]["ok"] is True
    assert (restore_artifacts / "dv_demo_001" / "canonical" / "animals.csv").exists()
    assert (restore_web / "uploads").is_dir()
    assert restore_db.exists()

    conn = connect(restore_db)
    try:
        rows = conn.execute("SELECT action FROM audit_log WHERE action='backup.restore' ORDER BY id DESC LIMIT 5").fetchall()
    finally:
        conn.close()
    assert rows, "backup.restore must be written to restored audit log"


def test_t13_06_step1_restore_detects_manifest_checksum_mismatch_before_install(tmp_path: Path):
    artifacts, web_storage, db_path = _prepare_source_tree(tmp_path)
    backup_zip = tmp_path / "backup.zip"
    _ = make_backup(artifacts_root=artifacts, web_storage=web_storage, db_path=db_path, out_zip=backup_zip)

    broken_zip = tmp_path / "backup_broken.zip"
    with zipfile.ZipFile(backup_zip, "r") as src, zipfile.ZipFile(broken_zip, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        manifest = json.loads(src.read("manifest.json").decode("utf-8"))
        for entry in manifest["entries"]:
            if entry["path"] == "artifacts/dv_demo_001/canonical/animals.csv":
                entry["sha256"] = "deadbeef"
                break
        for name in src.namelist():
            data = src.read(name)
            if name == "manifest.json":
                data = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            dst.writestr(name, data)

    restore_artifacts = tmp_path / "restore_bad" / "artifacts"
    restore_web = tmp_path / "restore_bad" / "web_storage"
    res = restore_backup(
        backup_zip=broken_zip,
        artifacts_root=restore_artifacts,
        web_storage=restore_web,
        db_path=restore_web / "web.db",
        force=True,
        smoke_check=True,
    )

    assert res["ok"] is False
    assert "checksum verification failed before restore" in res["reason"]
    assert res["mismatches"]
    assert not restore_artifacts.exists()

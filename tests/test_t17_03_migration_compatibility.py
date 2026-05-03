from __future__ import annotations

import json
import sqlite3
import zipfile
from hashlib import sha256
from pathlib import Path
from typing import Any

from genomeai.backup_restore import restore_backup
from genomeai.migration_pack_import import import_pilot_pack


def _sha256_bytes(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def _build_backup_v1_zip(path: Path, *, backup_format: str = "genomeai_backup_v1") -> Path:
    artifacts_file = b'{"ok": true}\n'
    db_bytes = sqlite3.connect(":memory:")
    # create simple sqlite payload on disk instead of memory dump for portability
    temp_db = path.parent / "_seed.db"
    conn = sqlite3.connect(temp_db)
    try:
        conn.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO sample(value) VALUES('ok')")
        conn.commit()
    finally:
        conn.close()
    db_payload = temp_db.read_bytes()

    web_file = b"log-line\n"
    manifest = {
        "format": backup_format,
        "backup_id": "backup_legacy",
        "created_at": "2026-03-20T00:00:00+00:00",
        "data_versions": ["dv_legacy"],
        "entries": [
            {
                "path": "artifacts/dv_legacy/reports/report.txt",
                "component": "artifacts",
                "rel_path": "dv_legacy/reports/report.txt",
                "sha256": _sha256_bytes(artifacts_file),
                "size": len(artifacts_file),
            },
            {
                "path": "web_storage/logs/app.log",
                "component": "web_storage",
                "rel_path": "logs/app.log",
                "sha256": _sha256_bytes(web_file),
                "size": len(web_file),
            },
            {
                "path": "web_storage/web.db",
                "component": "web_storage",
                "rel_path": "web.db",
                "sha256": _sha256_bytes(db_payload),
                "size": len(db_payload),
            },
        ],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("artifacts/dv_legacy/reports/report.txt", artifacts_file)
        zf.writestr("web_storage/logs/app.log", web_file)
        zf.writestr("web_storage/uploads/.gitkeep", b"")
        zf.writestr("web_storage/config_overrides/.gitkeep", b"")
        zf.writestr("web_storage/web.db", db_payload)
    temp_db.unlink(missing_ok=True)
    return path


def _build_pilot_pack_zip(path: Path, *, pack_schema_version: int = 1, aliases: bool = False) -> Path:
    if aliases:
        versions: dict[str, Any] = {
            "pack_schema_version": pack_schema_version,
            "dv": "dv_pack_legacy",
            "qc_run": "qc_pack_legacy",
            "mv": "model_pack_legacy",
            "sr": "score_pack_legacy",
            "rv": "report_pack_legacy",
            "pack_id": "pack_legacy",
        }
    else:
        versions = {
            "pack_schema_version": pack_schema_version,
            "data_version": "dv_pack_legacy",
            "qc_run": "qc_pack_legacy",
            "model_version": "model_pack_legacy",
            "scoring_run": "score_pack_legacy",
            "report_version": "report_pack_legacy",
            "pack_id": "pack_legacy",
        }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("versions.json", json.dumps(versions, ensure_ascii=False, indent=2))
        zf.writestr("canonical/dm_animals.csv", "animal_id\nA001\n")
        zf.writestr("qc/summary.json", "{}")
        zf.writestr("models/model.pkl", "placeholder")
        zf.writestr("scoring/predictions.csv", "animal_id,pred\nA001,1\n")
        zf.writestr("reports/report.md", "# report\n")
        zf.writestr("decisions/decision_log.json", "[]")
        zf.writestr("metadata/run_manifest.json", "{}")
    return path


def test_t17_03_restore_backup_accepts_supported_v1_archive(tmp_path: Path) -> None:
    backup_zip = _build_backup_v1_zip(tmp_path / "backup_v1.zip")
    artifacts_root = tmp_path / "restored_artifacts"
    web_storage = tmp_path / "restored_web"

    result = restore_backup(
        backup_zip=backup_zip,
        artifacts_root=artifacts_root,
        web_storage=web_storage,
        force=False,
        smoke_check=False,
    )

    assert result["ok"] is True
    assert (artifacts_root / "dv_legacy" / "reports" / "report.txt").exists()
    assert (web_storage / "web.db").exists()
    assert (web_storage / "logs" / "app.log").exists()


def test_t17_03_restore_backup_rejects_future_manifest_format_with_diagnostic(tmp_path: Path) -> None:
    backup_zip = _build_backup_v1_zip(tmp_path / "backup_future.zip", backup_format="genomeai_backup_v9")
    result = restore_backup(
        backup_zip=backup_zip,
        artifacts_root=tmp_path / "artifacts",
        web_storage=tmp_path / "web",
        force=False,
        smoke_check=False,
    )

    assert result["ok"] is False
    assert "newer than supported" in result["reason"]
    assert result["diagnostic"]["code"] == "migration.future_version"
    assert result["diagnostic"]["component"] == "backup_manifest"


def test_t17_03_import_pilot_pack_accepts_legacy_aliases(tmp_path: Path) -> None:
    pack_zip = _build_pilot_pack_zip(tmp_path / "pack_aliases.zip", aliases=True)
    artifacts_root = tmp_path / "artifacts"

    result = import_pilot_pack(pack_zip=pack_zip, artifacts_root=artifacts_root, verify=False, force=False)

    assert result["ok"] is True
    assert result["data_version"] == "dv_pack_legacy"
    assert (artifacts_root / "dv_pack_legacy" / "canonical" / "dm_animals.csv").exists()
    manifest_path = Path(str(result["import_manifest_json"]))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["compat"]["pack_schema_version"] == 1


def test_t17_03_import_pilot_pack_rejects_future_pack_schema_version(tmp_path: Path) -> None:
    pack_zip = _build_pilot_pack_zip(tmp_path / "pack_future.zip", pack_schema_version=9)
    result = import_pilot_pack(pack_zip=pack_zip, artifacts_root=tmp_path / "artifacts", verify=False, force=False)

    assert result["ok"] is False
    assert "newer than supported" in str(result["reason"])
    assert result["mismatches"][0]["code"] == "migration.future_version"
    assert result["mismatches"][0]["component"] == "pilot_pack"

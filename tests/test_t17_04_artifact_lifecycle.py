from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

from core.artifacts import archive_runtime_outputs, build_support_bundle, cleanup_runtime_outputs, load_artifact_lifecycle_policy
from web_cabinet.db import connect, init_db


def _write(path: Path, content: str, *, mtime: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _mkdir(path: Path, *, marker: str = "marker", mtime: int | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "marker.txt").write_text(marker, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _prepare_runtime_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    project_root = tmp_path / "project"
    artifacts_root = project_root / "artifacts"
    web_storage = project_root / "web_cabinet" / "storage"
    db_path = web_storage / "web.db"

    (project_root / "golden").mkdir(parents=True, exist_ok=True)
    _write(project_root / "golden" / "manifest.json", "{}\n", mtime=50)
    _mkdir(artifacts_root / "dv_keep" / "canonical", marker="dv", mtime=60)
    _write(artifacts_root / "manifest.json", "{}\n", mtime=61)

    _mkdir(artifacts_root / "_verify_refactor" / "verify_001", marker="v1", mtime=100)
    _mkdir(artifacts_root / "_verify_refactor" / "verify_002", marker="v2", mtime=200)
    _mkdir(artifacts_root / "_verify_refactor" / "verify_003", marker="v3", mtime=300)
    _mkdir(artifacts_root / "_verify_refactor" / "verify_004", marker="v4", mtime=400)
    _write(artifacts_root / "_verify_refactor" / "verify_004" / "verify_report.json", '{"ok": true}\n', mtime=401)
    _write(artifacts_root / "_verify_refactor" / "verify_004" / "verify_report.md", '# ok\n', mtime=401)

    _mkdir(artifacts_root / "_ci" / "run_001", marker="c1", mtime=100)
    _mkdir(artifacts_root / "_ci" / "run_002", marker="c2", mtime=200)
    _mkdir(artifacts_root / "_ci" / "run_003", marker="c3", mtime=300)
    _mkdir(artifacts_root / "_ci" / "run_004", marker="c4", mtime=400)

    _mkdir(project_root / "_tmp" / "tmp_001", marker="t1", mtime=100)
    _mkdir(project_root / "_tmp" / "tmp_002", marker="t2", mtime=200)
    _mkdir(project_root / "_tmp" / "tmp_003", marker="t3", mtime=300)
    _mkdir(project_root / "_tmp" / "tmp_004", marker="t4", mtime=400)
    _mkdir(project_root / "_tmp" / "tmp_005", marker="t5", mtime=500)
    _mkdir(project_root / "_tmp" / "tmp_006", marker="t6", mtime=600)

    _write(web_storage / "logs" / "app_001.log", "one\n", mtime=100)
    _write(web_storage / "logs" / "app_002.log", "two\n", mtime=200)
    _write(web_storage / "logs" / "app_003.log", "three\n", mtime=300)
    _write(web_storage / "uploads" / "keep.txt", "upload\n", mtime=50)

    backups_dir = artifacts_root / "backups"
    _write(backups_dir / "backup_001.zip", "old\n", mtime=100)
    _write(backups_dir / "backup_002.zip", "new\n", mtime=200)
    _mkdir(project_root / "artifacts_pre_restore_001", marker="restore-art-1", mtime=100)
    _mkdir(project_root / "artifacts_pre_restore_002", marker="restore-art-2", mtime=200)
    _mkdir(project_root / "storage_pre_restore_001", marker="restore-web-1", mtime=100)
    _mkdir(project_root / "storage_pre_restore_002", marker="restore-web-2", mtime=200)

    (project_root / "configs" / "ops").mkdir(parents=True, exist_ok=True)
    (project_root / "configs" / "ops" / "artifact_lifecycle_v1.yaml").write_text(
        """
version: 1
enabled: true
runtime_families:
  verify_reports:
    keep_last: 2
  ci_scratch:
    keep_last: 2
  tmp_workdirs:
    keep_last: 3
  web_logs:
    keep_last: 2
  runtime_archives:
    keep_last: 2
  support_bundles:
    keep_last: 2
support_bundle:
  max_log_files: 2
backup_retention:
  enabled: true
  include_data_versions_default: false
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (project_root / "configs" / "ops" / "backup_retention_v1.yaml").write_text(
        """
version: 1
enabled: true
apply_after_backup: false
backup_archives:
  keep_last: 1
restore_snapshots:
  enabled: true
  keep_last: 1
data_versions:
  enabled: false
  keep_last: 0
""".strip()
        + "\n",
        encoding="utf-8",
    )

    conn = connect(db_path)
    try:
        init_db(conn)
        conn.commit()
    finally:
        conn.close()
    return project_root, artifacts_root, web_storage


def test_t17_04_cleanup_runtime_outputs_is_safe_and_respects_retention(tmp_path: Path) -> None:
    project_root, artifacts_root, web_storage = _prepare_runtime_tree(tmp_path)

    dry_run = cleanup_runtime_outputs(
        project_root=project_root,
        artifacts_root=artifacts_root,
        web_storage=web_storage,
        dry_run=True,
    )
    assert len(dry_run["runtime_families"]["verify_reports"]["delete_candidates"]) == 2
    assert len(dry_run["runtime_families"]["ci_scratch"]["delete_candidates"]) == 2
    assert len(dry_run["runtime_families"]["tmp_workdirs"]["delete_candidates"]) == 3
    assert len(dry_run["runtime_families"]["web_logs"]["delete_candidates"]) == 1
    assert len(dry_run["backup_retention"]["backups"]["delete_candidates"]) == 1
    assert (project_root / "golden" / "manifest.json").exists()
    assert (artifacts_root / "dv_keep").exists()
    assert (web_storage / "uploads" / "keep.txt").exists()

    applied = cleanup_runtime_outputs(
        project_root=project_root,
        artifacts_root=artifacts_root,
        web_storage=web_storage,
        dry_run=False,
    )
    assert len(applied["runtime_families"]["verify_reports"]["deleted_paths"]) == 2
    assert len(applied["runtime_families"]["ci_scratch"]["deleted_paths"]) == 2
    assert len(applied["runtime_families"]["tmp_workdirs"]["deleted_paths"]) == 3
    assert len(applied["runtime_families"]["web_logs"]["deleted_paths"]) == 1
    assert len(applied["backup_retention"]["backups"]["deleted_paths"]) == 1
    assert len(list((artifacts_root / "_verify_refactor").glob("verify_*"))) == 2
    assert len(list((artifacts_root / "_ci").glob("run_*"))) == 2
    assert len(list((project_root / "_tmp").glob("tmp_*"))) == 3
    assert len(list((web_storage / "logs").glob("*.log"))) == 2
    assert len(list((artifacts_root / "backups").glob("*.zip"))) == 1
    assert (project_root / "golden" / "manifest.json").exists()
    assert (artifacts_root / "dv_keep").exists()
    assert (web_storage / "uploads" / "keep.txt").exists()

    conn = connect(web_storage / "web.db")
    try:
        rows = conn.execute("SELECT action FROM audit_log WHERE action='artifact.cleanup' ORDER BY id DESC").fetchall()
    finally:
        conn.close()
    assert rows


def test_t17_04_runtime_archive_contains_only_selected_runtime_families(tmp_path: Path) -> None:
    project_root, artifacts_root, web_storage = _prepare_runtime_tree(tmp_path)
    out_zip = artifacts_root / "_archive" / "runtime_archive_test.zip"
    result = archive_runtime_outputs(
        output_zip=out_zip,
        project_root=project_root,
        artifacts_root=artifacts_root,
        web_storage=web_storage,
        families=["verify_reports", "tmp_workdirs"],
        scope="delete_candidates",
    )
    assert result["ok"] is True
    with zipfile.ZipFile(out_zip, "r") as zf:
        names = sorted(zf.namelist())
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    assert any(name.startswith("runtime/verify_reports/") for name in names)
    assert any(name.startswith("runtime/tmp_workdirs/") for name in names)
    assert all(not name.startswith("runtime/ci_scratch/") for name in names)
    assert all("golden" not in name for name in names)
    assert manifest["scope"] == "delete_candidates"
    assert manifest["families"] == ["verify_reports", "tmp_workdirs"]


def test_t17_04_support_bundle_is_deterministic_and_contains_diagnostics(tmp_path: Path) -> None:
    project_root, artifacts_root, web_storage = _prepare_runtime_tree(tmp_path)
    bundle_a = artifacts_root / "support_bundles" / "bundle_a.zip"
    bundle_b = artifacts_root / "support_bundles" / "bundle_b.zip"

    result_a = build_support_bundle(
        output_zip=bundle_a,
        project_root=project_root,
        artifacts_root=artifacts_root,
        web_storage=web_storage,
    )
    result_b = build_support_bundle(
        output_zip=bundle_b,
        project_root=project_root,
        artifacts_root=artifacts_root,
        web_storage=web_storage,
    )
    assert result_a["ok"] and result_b["ok"]
    assert hashlib.sha256(bundle_a.read_bytes()).hexdigest() == hashlib.sha256(bundle_b.read_bytes()).hexdigest()

    with zipfile.ZipFile(bundle_a, "r") as zf:
        names = sorted(zf.namelist())
        env_snapshot = json.loads(zf.read("diagnostics/environment_snapshot.json").decode("utf-8"))
        inventory = json.loads(zf.read("diagnostics/runtime_inventory.json").decode("utf-8"))
        db_summary = json.loads(zf.read("diagnostics/web_db_summary.json").decode("utf-8"))
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))

    assert "configs/artifact_lifecycle_v1.yaml" in names
    assert "configs/backup_retention_v1.yaml" in names
    assert "diagnostics/environment_snapshot.json" in names
    assert "diagnostics/runtime_inventory.json" in names
    assert "diagnostics/web_db_summary.json" in names
    assert any(name.startswith("verify/verify_004/") for name in names)
    assert any(name.startswith("logs/") for name in names)
    assert env_snapshot["version"] == 1
    assert "families" in inventory
    assert db_summary["exists"] is True
    assert manifest["schema"] == "genomeai.support_bundle.v1"


def test_t17_04_policy_loader_exposes_expected_runtime_families(tmp_path: Path) -> None:
    project_root, *_ = _prepare_runtime_tree(tmp_path)
    policy = load_artifact_lifecycle_policy(project_root=project_root)
    assert policy["version"] == 1
    assert set(policy["runtime_families"]) >= {"verify_reports", "ci_scratch", "tmp_workdirs", "runtime_archives", "support_bundles", "web_logs"}

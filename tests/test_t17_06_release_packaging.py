from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.release import build_release_package, load_release_metadata, run_release_package_smoke


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_t17_06_release_metadata_defaults_are_stable(monkeypatch) -> None:
    monkeypatch.delenv("GENOMEAI_BUILD_STAMP", raising=False)
    monkeypatch.delenv("GENOMEAI_RELEASE_CHANNEL", raising=False)
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    metadata = load_release_metadata(project_root=".")
    assert metadata["version"] == "0.0.1"
    assert metadata["build_stamp"] == "local"
    assert metadata["release_channel"] == "dev"
    assert metadata["build_time_utc"] == "1980-01-01T00:00:00+00:00"


def test_t17_06_release_build_is_reproducible(tmp_path: Path) -> None:
    first = build_release_package(project_root=".", out_path=tmp_path / "release_a.zip", build_stamp="ci", release_channel="ci", source_date_epoch=315532800)
    second = build_release_package(project_root=".", out_path=tmp_path / "release_b.zip", build_stamp="ci", release_channel="ci", source_date_epoch=315532800)
    assert _sha256(Path(first["archive_path"])) == _sha256(Path(second["archive_path"]))
    manifest = json.loads(Path(first["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["metadata"]["build_stamp"] == "ci"
    assert manifest["metadata"]["release_channel"] == "ci"
    assert manifest["file_count"] > 20


def test_t17_06_release_smoke_validates_packaged_interfaces(tmp_path: Path) -> None:
    built = build_release_package(project_root=".", out_path=tmp_path / "release.zip", build_stamp="smoke", release_channel="test", source_date_epoch=315532800)
    result = run_release_package_smoke(archive_path=built["archive_path"])
    assert result["ok"] is True
    assert result["manifest"]["ok"] is True
    assert result["cli"]["version"] == "0.0.1"
    assert result["api"]["health_status"] == 200
    assert result["api"]["release_status"] == 200
    assert result["api"]["login_contains_version"] is True

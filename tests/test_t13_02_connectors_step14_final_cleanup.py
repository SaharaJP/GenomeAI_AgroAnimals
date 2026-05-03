from __future__ import annotations

from pathlib import Path

import pytest

from genomeai.cli import build_parser
from genomeai.connectors_v1 import ConnectorConfigError, cleanup_connector_temp_files, list_connector_temp_files, save_connector_config



def _write_mapping(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("columns:\n  FarmID: farm_id\n", encoding="utf-8")



def test_save_connector_config_validation_failure_does_not_leave_tmp_yaml(tmp_path: Path):
    project_root = tmp_path / "project"
    source_dir = project_root / "inbox"
    source_dir.mkdir(parents=True, exist_ok=True)
    mapping_path = project_root / "configs" / "mappings" / "farms_example.yaml"
    _write_mapping(mapping_path)
    config_path = project_root / "configs" / "connectors" / "broken.yaml"
    tmp_yaml = config_path.with_suffix(config_path.suffix + ".tmp")

    with pytest.raises(ConnectorConfigError):
        save_connector_config(
            config_path=config_path,
            project_root=project_root,
            connector_id="broken_connector",
            kind="file",
            enabled=True,
            description="broken schedule cleanup test",
            source_dir=str(source_dir),
            schedule="not a cron",
            data_version_template="dv_%Y%m%d_%H%M%S",
            bindings=[
                {
                    "dataset_key": "farms",
                    "pattern": "farms.csv",
                    "mapping": str(mapping_path),
                    "required": True,
                }
            ],
            retry_policy=None,
            preserve_unknown=False,
        )

    assert not config_path.exists()
    assert not tmp_yaml.exists(), "broken save must not leave *.yaml.tmp behind"



def test_cleanup_connector_temp_files_lists_and_removes_stale_files(tmp_path: Path):
    configs_dir = tmp_path / "configs" / "connectors"
    configs_dir.mkdir(parents=True, exist_ok=True)
    stale_a = configs_dir / ".__preview__deadbeef.yaml.tmp"
    stale_b = configs_dir / "bad_ui_deadbeef.yaml.tmp"
    good = configs_dir / "file_demo.yaml"
    stale_a.write_text("x: 1\n", encoding="utf-8")
    stale_b.write_text("x: 1\n", encoding="utf-8")
    good.write_text("connector_id: ok\nkind: api_stub\ndatasets:\n  - dataset_key: farms\n    path: /tmp/farms.csv\n    mapping: /tmp/map.yaml\n", encoding="utf-8")

    listed = [p.name for p in list_connector_temp_files(configs_dir)]
    assert listed == [".__preview__deadbeef.yaml.tmp", "bad_ui_deadbeef.yaml.tmp"]

    removed = [p.name for p in cleanup_connector_temp_files(configs_dir, remove=True)]
    assert removed == listed
    assert not stale_a.exists()
    assert not stale_b.exists()
    assert good.exists()



def test_repo_configs_connectors_directory_is_clean_after_finalization():
    repo_root = Path(__file__).resolve().parents[1]
    configs_dir = repo_root / "configs" / "connectors"
    stale = list_connector_temp_files(configs_dir)
    assert stale == [], f"stale connector temp files must not be packaged: {[p.name for p in stale]}"
    packaged = sorted(p.name for p in configs_dir.glob("*.y*ml"))
    assert packaged == ["api_stub_demo.yaml", "file_demo.yaml", "onec_stub_demo.yaml"]



def test_cli_connectors_cleanup_dry_run_reports_stale_count(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    configs_dir = tmp_path / "configs" / "connectors"
    configs_dir.mkdir(parents=True, exist_ok=True)
    (configs_dir / ".__preview__cafebabe.yaml.tmp").write_text("x: 1\n", encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args(["connectors", "cleanup", "--configs-dir", str(configs_dir), "--dry-run"])
    rc = args.func(args)
    out = capsys.readouterr().out

    assert rc == 0
    assert "CONNECTOR_CLEANUP_DRY_RUN" in out
    assert "stale_count=1" in out
    assert ".__preview__cafebabe.yaml.tmp" in out
    assert (configs_dir / ".__preview__cafebabe.yaml.tmp").exists(), "dry-run must not delete files"

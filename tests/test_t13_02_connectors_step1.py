from __future__ import annotations

from pathlib import Path

from genomeai.connectors_v1 import load_connector_spec, run_connector_config



def _write_sources(base: Path, *, milk_305: int = 10000) -> None:
    base.mkdir(parents=True, exist_ok=True)
    (base / "farms.csv").write_text(
        "FarmID,Name,Reg,Country,Latitude,Longitude,Created,Active\n"
        "F1,Farm 1,MSK,RU,55.1,37.2,2025-01-01,true\n",
        encoding="utf-8",
    )
    (base / "animals.csv").write_text(
        "AnimalID,FarmID,EarTag,Breed,Sex,Birth,Alive,Status\n"
        "A1,F1,1001,HO,F,2022-01-01,true,active\n",
        encoding="utf-8",
    )
    (base / "lactations.csv").write_text(
        "AnimalID,LactNo,Calving,Dryoff,DIM,Milk305,Fat,Protein\n"
        f"A1,1,2025-01-10,2025-11-10,305,{milk_305},3.9,3.2\n",
        encoding="utf-8",
    )



def test_file_connector_increment_and_manifest(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    inbox = tmp_path / "inbox"
    artifacts = tmp_path / "artifacts"
    _write_sources(inbox, milk_305=10000)

    config_path = tmp_path / "file_connector.yaml"
    config_path.write_text(
        "\n".join(
            [
                "connector_id: farm_file",
                "kind: file",
                "enabled: true",
                f"source_dir: {inbox}",
                'schedule: "*/15 * * * *"',
                'data_version_template: "dv_file_%Y%m%d_%H%M%S"',
                "datasets:",
                f"  - dataset_key: farms\n    pattern: 'farms.csv'\n    mapping: {repo_root / 'configs/mappings/farms_example.yaml'}",
                f"  - dataset_key: animals\n    pattern: 'animals.csv'\n    mapping: {repo_root / 'configs/mappings/animals_example.yaml'}",
                f"  - dataset_key: lactations\n    pattern: 'lactations.csv'\n    mapping: {repo_root / 'configs/mappings/lactations_example.yaml'}",
            ]
        ),
        encoding="utf-8",
    )

    spec = load_connector_spec(config_path, project_root=repo_root)
    first = run_connector_config(config_path, project_root=repo_root, artifacts_root=artifacts, trigger_type="manual")
    assert first.ok is True
    assert first.status == "success"
    assert first.data_version
    manifest = artifacts / first.data_version / "connectors" / first.connector_run_id / "manifest.json"
    assert manifest.exists()
    assert (artifacts / first.data_version / "canonical" / "dm_animals.csv").exists()
    assert (artifacts / first.data_version / "canonical" / "dm_lactations.csv").exists()

    second = run_connector_config(config_path, project_root=repo_root, artifacts_root=artifacts, trigger_type="manual")
    assert second.ok is True
    assert second.status == "noop"
    assert "no new or changed files" in second.message.lower()

    _write_sources(inbox, milk_305=11111)
    third = run_connector_config(config_path, project_root=repo_root, artifacts_root=artifacts, trigger_type="manual")
    assert third.ok is True
    assert third.status == "success"
    assert third.data_version and third.data_version != first.data_version
    assert spec.connector_id == "farm_file"
    lact_text = (artifacts / third.data_version / "canonical" / "dm_lactations.csv").read_text(encoding="utf-8")
    assert "11111" in lact_text



def test_stub_connectors_return_readable_stub_status(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    config_path = tmp_path / "api_stub.yaml"
    config_path.write_text(
        "\n".join(
            [
                "connector_id: stub_api",
                "kind: api_stub",
                "enabled: true",
                'schedule: "@daily"',
                "datasets:",
                f"  - dataset_key: animals\n    path: {repo_root / 'data/examples/external/animals.csv'}\n    mapping: {repo_root / 'configs/mappings/animals_example.yaml'}\n    required: false",
            ]
        ),
        encoding="utf-8",
    )
    res = run_connector_config(config_path, project_root=repo_root, artifacts_root=tmp_path / "artifacts", trigger_type="manual")
    assert res.ok is True
    assert res.status == "stub"
    assert "stub" in res.message.lower()

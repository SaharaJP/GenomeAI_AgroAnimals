from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from streamlit_app.upload_ingest import (
    dataset_status_rows,
    mapping_contract_coverage,
    publish_upload_version,
    set_dataset_validation_state,
    summarize_dataset_completeness,
)
from web_cabinet import rbac


REPO_ROOT = Path(__file__).resolve().parents[1]


def _ctx(tmp_path: Path):
    web_storage_dir = tmp_path / "web_storage"
    artifacts_dir = tmp_path / "artifacts"
    web_storage_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(web_storage_dir=web_storage_dir, artifacts_dir=artifacts_dir)


def _user(role: str) -> dict[str, object]:
    return {
        "id": 1,
        "username": role.lower(),
        "role": role,
        "tenant_id": "default",
        "permissions": list(rbac.ROLE_PERMISSIONS.get(role, [])),
        "request_id": "st-test-t19-03",
    }


def test_t19_03_mapping_coverage_detects_required_field_gaps(tmp_path: Path) -> None:
    mapping_path = tmp_path / "animals_partial.yaml"
    mapping_path.write_text(
        "dataset: animals\ncolumns:\n  animal_id: animal_id\n",
        encoding="utf-8",
    )

    coverage = mapping_contract_coverage(dataset_key="animals", mapping_path=mapping_path)
    assert "farm_id" in coverage["missing_required_fields"]
    assert "animal_id" in coverage["covered_target_fields"]
    assert coverage["is_ready_for_validation"] is False


def test_t19_03_readiness_summary_includes_mapping_and_validation_state(tmp_path: Path) -> None:
    example = REPO_ROOT / "data" / "examples" / "dm_animals.csv"
    mapping_path = REPO_ROOT / "configs" / "mappings" / "animals_example.yaml"
    session_like: dict[str, object] = {
        "upload.animals.file_name": example.name,
        "upload.animals.file_path": str(example),
        "upload.animals.mapping_name": str(mapping_path.relative_to(REPO_ROOT)),
        "upload.animals.mapping_path": str(mapping_path),
    }
    set_dataset_validation_state(session_like, "animals", {"dataset_key": "animals", "ok": False, "status": "failed", "error_count": 2})

    rows = dataset_status_rows(session_like=session_like, data_version="dv_t19_03")
    animals = next(row for row in rows if row["dataset_key"] == "animals")
    assert animals["mapping_missing_required_fields"] == []
    assert animals["validation_status"] == "failed"
    assert animals["ingest_ready"] is False

    summary = summarize_dataset_completeness(session_like=session_like, data_version="dv_t19_03")
    assert "animals" in summary["validation_failed"]
    assert summary["can_publish"] is False


def test_t19_03_publish_version_writes_manifest(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    payload = publish_upload_version(
        ctx,
        user=_user(rbac.ROLE_OPERATOR),
        data_version="dv_t19_03_publish",
        datasets=[
            {
                "dataset_key": "farms",
                "file_path": str(REPO_ROOT / "data" / "examples" / "dm_farms.csv"),
                "mapping_path": str(REPO_ROOT / "configs" / "mappings" / "farms_example.yaml"),
            }
        ],
        validation_results=[{"dataset_key": "farms", "ok": True, "status": "ok", "rows_in": 3}],
    )
    assert payload["ok"] is True
    manifest_path = Path(str(payload["manifest_path"]))
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "genomeai.streamlit.upload_publish.v1"
    assert manifest["data_version"] == "dv_t19_03_publish"
    assert manifest["datasets"][0]["validation"]["ok"] is True


def test_t19_03_docs_and_gate_reference_upload_ux() -> None:
    doc = Path("docs/streamlit_upload_ux.md").read_text(encoding="utf-8")
    gate = Path("ci/pytest_gate.txt").read_text(encoding="utf-8")
    page = Path("streamlit_app/pages/26_Upload_And_Ingest_Wizard.py").read_text(encoding="utf-8")
    adapter = Path("streamlit_app/upload_ingest.py").read_text(encoding="utf-8")
    assumptions = Path("docs/assumptions.md").read_text(encoding="utf-8")

    assert "files → preview → mapping → validate → publish version → run ingest" in doc
    assert "dataset readiness" in doc.lower()
    assert "tests/test_t19_03_upload_ingest_ux.py" in gate
    assert "publish_upload_version" in page
    assert "build_error_payload" in adapter
    assert "T19-03" in assumptions

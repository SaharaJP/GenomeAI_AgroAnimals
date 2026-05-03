from __future__ import annotations

import importlib
import os
from pathlib import Path
from types import SimpleNamespace

from streamlit_app.upload_ingest import (
    build_identity_mapping_bytes,
    contract_precheck_dataset,
    default_mapping_for_dataset,
    launch_ingest_jobs,
    list_dataset_specs,
    mapping_options_for_dataset,
    save_named_upload_bytes,
    summarize_dataset_completeness,
)
from streamlit_app.unified_shell import build_shell_for_user, flatten_shell_sections, load_shell_config
from web_cabinet import rbac


def _ctx(tmp_path: Path):
    return SimpleNamespace(web_storage_dir=tmp_path / "web", artifacts_dir=tmp_path / "artifacts")


def _user(role: str) -> dict[str, object]:
    return {
        "id": 1,
        "username": role.lower(),
        "role": role,
        "tenant_id": "default",
        "permissions": list(rbac.ROLE_PERMISSIONS.get(role, [])),
        "request_id": "st-test-upload",
    }


def test_t18_04_mapping_options_cover_required_datasets() -> None:
    specs = {spec.dataset_key: spec for spec in list_dataset_specs()}
    assert specs["farms"].required is True
    assert specs["animals"].required is True
    assert specs["lactations"].required is True
    assert default_mapping_for_dataset("farms") == "configs/mappings/farms_example.yaml"
    assert default_mapping_for_dataset("animals") == "configs/mappings/animals_example.yaml"
    assert default_mapping_for_dataset("lactations") == "configs/mappings/lactations_example.yaml"
    assert "configs/mappings/testday_example.yaml" in mapping_options_for_dataset("testday")


def test_t18_04_dataset_completeness_tracks_missing_required() -> None:
    session_like = {
        "upload.farms.file_name": "dm_farms.csv",
        "upload.farms.mapping_name": "configs/mappings/farms_example.yaml",
        "upload.animals.file_name": "dm_animals.csv",
        # animals mapping missing
        "upload.lactations.file_name": "dm_lactations.csv",
        "upload.lactations.mapping_name": "configs/mappings/lactations_example.yaml",
    }
    summary = summarize_dataset_completeness(session_like=session_like, data_version="dv_t18_04")
    assert summary["can_launch"] is False
    assert "animals" in summary["missing_required"]
    assert "farms" in summary["ready_datasets"]
    assert "lactations" in summary["ready_datasets"]


def test_t18_04_upload_ingest_shell_visible_for_operator_hidden_for_viewer() -> None:
    cfg = load_shell_config(Path("configs/ui/ia_v3.yaml"))
    operator_sections = build_shell_for_user(
        cfg=cfg,
        role=rbac.ROLE_OPERATOR,
        permissions=set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_OPERATOR, [])),
    )
    viewer_sections = build_shell_for_user(
        cfg=cfg,
        role=rbac.ROLE_VIEWER,
        permissions=set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_VIEWER, [])),
    )
    assert "upload_ingest_wizard" in flatten_shell_sections(operator_sections)
    assert "upload_ingest_wizard" not in flatten_shell_sections(viewer_sections)


def test_t18_04_viewer_cannot_launch_ingest(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    res = launch_ingest_jobs(ctx, user=_user(rbac.ROLE_VIEWER), data_version="dv_x", datasets=[])
    assert res.ok is False
    assert res.errors
    assert res.errors[0]["error"] == "permission_denied"


def test_t18_04_launch_ingest_and_worker_smoke(tmp_path: Path, monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    ctx = _ctx(tmp_path)
    monkeypatch.setenv("GENOMEAI_PROJECT_ROOT", str(repo_root))
    monkeypatch.setenv("GENOMEAI_ARTIFACTS_ROOT", str(ctx.artifacts_dir))
    monkeypatch.setenv("GENOMEAI_WEB_STORAGE", str(ctx.web_storage_dir))
    monkeypatch.setenv("GENOMEAI_WEB_DISABLE_WORKER", "1")

    base = repo_root / "data" / "examples"
    farms_path = save_named_upload_bytes(ctx, filename="dm_farms.csv", content=(base / "dm_farms.csv").read_bytes())
    animals_path = save_named_upload_bytes(ctx, filename="dm_animals.csv", content=(base / "dm_animals.csv").read_bytes())
    lact_path = save_named_upload_bytes(ctx, filename="dm_lactations.csv", content=(base / "dm_lactations.csv").read_bytes())

    identity_mappings = {}
    for dataset_key, file_path in (("farms", farms_path), ("animals", animals_path), ("lactations", lact_path)):
        mapping_path = save_named_upload_bytes(
            ctx,
            filename=f"{dataset_key}_identity.yaml",
            content=build_identity_mapping_bytes(dataset_key=dataset_key, file_path=file_path),
            is_mapping=True,
        )
        identity_mappings[dataset_key] = mapping_path
        precheck = contract_precheck_dataset(
            dataset_key=dataset_key,
            file_path=file_path,
            mapping_path=mapping_path,
        )
        assert precheck["ok"] is True

    result = launch_ingest_jobs(
        ctx,
        user=_user(rbac.ROLE_OPERATOR),
        data_version="dv_t18_04_smoke",
        datasets=[
            {"dataset_key": "farms", "file_path": str(farms_path), "mapping_path": str(identity_mappings["farms"])},
            {"dataset_key": "animals", "file_path": str(animals_path), "mapping_path": str(identity_mappings["animals"])},
            {"dataset_key": "lactations", "file_path": str(lact_path), "mapping_path": str(identity_mappings["lactations"])},
        ],
    )
    assert result.created_jobs
    assert len(result.created_jobs) == 3

    worker_module = importlib.import_module("web_cabinet.worker")
    worker_module = importlib.reload(worker_module)
    worker = worker_module.JobWorker()
    worker.run_until_empty(max_jobs=50)

    canonical = ctx.artifacts_dir / "dv_t18_04_smoke" / "canonical"
    assert (canonical / "dm_farms.csv").exists()
    assert (canonical / "dm_animals.csv").exists()
    assert (canonical / "dm_lactations.csv").exists()

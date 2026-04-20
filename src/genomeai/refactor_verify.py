from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from core.application.refactor_verify_compare import (
    FileDiff,
    ScenarioReport,
    VerifyReport,
    compare_snapshot_dirs,
    render_markdown,
    verify_report_payload,
)
from core.application.refactor_verify_runtime import (
    SCENARIOS,
    ScenarioSpec,
    get_scenario_spec,
    golden_manifest_path,
    resolve_scenario_specs,
    resolve_verify_report_root,
    select_scenario_names,
)
from .contracts import load_contracts_dir
from .decision_log import init_decision_log
from .ingest import ingest_dataset
from .qc import run_qc
from .report import generate_report_text_fallback, run_report
from .score import run_scoring
from .train import train_productivity_model


VOLATILE_JSON_KEYS = {
    "created_at",
    "created_at_utc",
    "updated_at",
    "updated_at_utc",
    "timestamp",
    "ts",
    "fact_pack_hash",
    "pack_id",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _round_value(value: Any, digits: int = 6) -> Any:
    if isinstance(value, float):
        return round(value, digits)
    return value


def _normalize_scalar(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        if pd.isna(value):
            return None
        return round(value, 6)
    return str(value)


def _normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in sorted(value.keys()):
            if key in VOLATILE_JSON_KEYS:
                continue
            out[key] = _normalize_json(value[key])
        return out
    if isinstance(value, list):
        return [_normalize_json(v) for v in value]
    return _normalize_scalar(value)


def _stable_json_text(value: Any) -> str:
    return json.dumps(_normalize_json(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    _write_text(path, _stable_json_text(value))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_file_index(root: Path) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    if not root.exists():
        return files
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = str(path.relative_to(root)).replace("\\", "/")
        files.append(
            {
                "path": rel,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    return files


def _manifest_total_bytes(entries: list[dict[str, Any]]) -> int:
    return int(sum(int(item.get("size_bytes") or 0) for item in entries))


def _normalize_dataframe(df: pd.DataFrame, *, columns: list[str], sort_by: list[str]) -> list[dict[str, Any]]:
    out = df.copy()
    keep = [c for c in columns if c in out.columns]
    out = out[keep].copy()
    for col in out.columns:
        if pd.api.types.is_numeric_dtype(out[col]):
            out[col] = out[col].map(lambda v: None if pd.isna(v) else round(float(v), 6))
        else:
            out[col] = out[col].map(lambda v: "" if pd.isna(v) else str(v))
    by = [c for c in sort_by if c in out.columns]
    if by:
        out = out.sort_values(by=by, kind="stable").reset_index(drop=True)
    return [{k: _normalize_scalar(v) for k, v in row.items()} for row in out.to_dict(orient="records")]


def _project_root(default: Path | None = None) -> Path:
    return Path(os.environ.get("GENOMEAI_PROJECT_ROOT", str(default or Path.cwd()))).resolve()


def _prepare_standard_inputs(project_root: Path, dst: Path) -> None:
    src = project_root / "data" / "examples" / "external"
    dst.mkdir(parents=True, exist_ok=True)
    for p in src.glob("*.csv"):
        shutil.copy2(p, dst / p.name)


def _prepare_qc_inputs(project_root: Path, dst: Path) -> None:
    _prepare_standard_inputs(project_root, dst)
    animals_path = dst / "animals_ext.csv"
    lactations_path = dst / "lactations_ext.csv"

    animals = pd.read_csv(animals_path)
    animals.loc[len(animals)] = ["A003", "F001", "12347", "Holstein", "F", "2021-06-15", True, "LACTATING"]
    animals.to_csv(animals_path, index=False)

    lactations = pd.read_csv(lactations_path)
    lactations.loc[0, "Milk305"] = 19000
    lactations.to_csv(lactations_path, index=False)


INPUT_PREPARERS = {
    "standard": _prepare_standard_inputs,
    "qc_issues": _prepare_qc_inputs,
}


def ensure_golden_inputs(*, golden_root: Path, project_root: Path) -> None:
    for scenario_name, preparer in INPUT_PREPARERS.items():
        inputs_dir = golden_root / "scenarios" / scenario_name / "inputs" / "external"
        if inputs_dir.exists() and any(inputs_dir.glob("*.csv")):
            continue
        shutil.rmtree(inputs_dir.parent, ignore_errors=True)
        inputs_dir.mkdir(parents=True, exist_ok=True)
        preparer(project_root, inputs_dir)


def _seed_web_state(
    *,
    project_root: Path,
    web_storage_dir: Path,
    scenario: ScenarioSpec,
    first_object_id: str,
) -> tuple[Path, list[dict[str, Any]], list[dict[str, Any]]]:
    os.environ["GENOMEAI_PROJECT_ROOT"] = str(project_root)
    os.environ["GENOMEAI_WEB_STORAGE"] = str(web_storage_dir)
    from core.audit.events import write_audit
    from core.infra.web_db import connect, init_db
    from web_cabinet.tasks_v1 import TaskCreate, create_task, list_tasks

    db_path = web_storage_dir / "web.db"
    web_storage_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    init_db(conn)

    task_id = create_task(
        conn,
        tenant_id="default",
        t=TaskCreate(
            task_type="verify_refactor.review",
            title=f"Verify {scenario.name} recommendation",
            domain="data",
            priority=2,
            due_at="2026-01-01T00:00:00+00:00",
            assignee_team="team-data",
            object_type="animal",
            object_id=first_object_id,
            data_version=scenario.data_version,
            qc_run=scenario.qc_run,
            model_version=scenario.model_version,
            scoring_run=scenario.scoring_run,
            report_version=scenario.report_version,
            dedupe_key=f"verify_refactor:{scenario.name}:{first_object_id}",
        ),
    )
    write_audit(
        conn,
        tenant_id="default",
        user_id=1,
        username="admin",
        role="admin",
        action="verify_refactor.task_seeded",
        object_type="task",
        object_id=task_id,
        data_version=scenario.data_version,
        run_id=scenario.scoring_run,
        after={"scenario": scenario.name, "task_id": task_id},
    )
    write_audit(
        conn,
        tenant_id="default",
        user_id=1,
        username="admin",
        role="admin",
        action="verify_refactor.report_seeded",
        object_type="report",
        object_id=scenario.report_version,
        data_version=scenario.data_version,
        run_id=scenario.report_version,
        after={"scenario": scenario.name, "report_version": scenario.report_version},
    )

    tasks_rows = list_tasks(conn, tenant_id="default", limit=50, offset=0).get("rows", [])
    audit_rows = [dict(r) for r in conn.execute("SELECT * FROM audit_log WHERE tenant_id=? ORDER BY action, object_id", ("default",)).fetchall()]
    conn.close()
    return db_path, tasks_rows, audit_rows


def _normalize_tasks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda r: (str(r.get("title") or ""), str(r.get("object_id") or "")))
    keep = [
        "task_type",
        "title",
        "domain",
        "priority",
        "status",
        "due_at",
        "assignee_team",
        "stage",
        "related_alert",
        "object_type",
        "object_id",
        "data_version",
        "qc_run",
        "model_version",
        "scoring_run",
        "report_version",
        "dedupe_key",
    ]
    return [{k: _normalize_scalar(row.get(k)) for k in keep} for row in ordered]


def _normalize_audit(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda r: (str(r.get("action") or ""), str(r.get("object_id") or "")))
    keep = [
        "tenant_id",
        "username",
        "role",
        "action",
        "action_group",
        "object_type",
        "object_id",
        "data_version",
        "run_id",
        "status",
    ]
    normalized: list[dict[str, Any]] = []
    for row in ordered:
        item = {k: _normalize_scalar(row.get(k)) for k in keep}
        if item.get("action") == "verify_refactor.task_seeded" and item.get("object_type") == "task":
            item["object_id"] = "<task_id>"
        normalized.append(item)
    return normalized


def _normalize_qc_summary(path: Path) -> dict[str, Any]:
    raw = _read_json(path)
    return {
        "schema": raw.get("schema"),
        "data_version": raw.get("data_version"),
        "qc_run": raw.get("qc_run"),
        "qc_status": raw.get("qc_status"),
        "datasets_loaded": raw.get("datasets_loaded") or [],
        "issue_counts": raw.get("issue_counts") or {},
        "metrics": raw.get("metrics") or {},
        "row_counts": raw.get("row_counts") or {},
    }


def _normalize_scoring_summary(path: Path) -> dict[str, Any]:
    raw = _read_json(path)
    return {
        "schema": raw.get("schema"),
        "data_version": raw.get("data_version"),
        "model_version": raw.get("model_version"),
        "scoring_run": raw.get("scoring_run"),
        "row_counts": raw.get("row_counts") or {},
        "status": raw.get("status"),
    }


def _normalize_report_summary(path: Path) -> dict[str, Any]:
    raw = _read_json(path)
    return {
        "schema": raw.get("schema"),
        "data_version": raw.get("data_version"),
        "qc_run": raw.get("qc_run"),
        "model_version": raw.get("model_version"),
        "scoring_run": raw.get("scoring_run"),
        "report_version": raw.get("report_version"),
        "mode_requested": raw.get("mode_requested"),
        "llm_used": raw.get("llm_used"),
        "outputs": {
            "report_docx_exists": Path(str((raw.get("outputs") or {}).get("report_docx") or "")).exists(),
            "report_pdf_exists": Path(str((raw.get("outputs") or {}).get("report_pdf") or "")).exists() if str((raw.get("outputs") or {}).get("report_pdf") or "") not in ("", "NA") else False,
        },
    }


def _normalize_fact_pack(path: Path) -> dict[str, Any]:
    raw = _read_json(path)
    playbooks = raw.get("playbooks", {}) or {}
    recommended = playbooks.get("recommended") or []
    return {
        "schema": raw.get("schema"),
        "versions": raw.get("versions") or {},
        "qc": {
            "qc_status": ((raw.get("qc") or {}).get("qc_status")),
            "datasets_loaded": ((raw.get("qc") or {}).get("datasets_loaded") or []),
            "metrics": ((raw.get("qc") or {}).get("metrics") or {}),
        },
        "ml": {
            "task": ((raw.get("ml") or {}).get("task")),
            "target": ((raw.get("ml") or {}).get("target")),
            "features": ((raw.get("ml") or {}).get("features") or {}),
            "split": ((raw.get("ml") or {}).get("split") or {}),
            "metrics": ((raw.get("ml") or {}).get("metrics") or {}),
            "limitations": ((raw.get("ml") or {}).get("limitations") or {}),
        },
        "scoring": {
            "status": ((raw.get("scoring") or {}).get("status")),
            "row_counts": ((raw.get("scoring") or {}).get("row_counts") or {}),
            "confidence_counts": ((raw.get("scoring") or {}).get("confidence_counts") or {}),
        },
        "top_lists": raw.get("top_lists") or {},
        "distributions": raw.get("distributions") or {},
        "temporal": raw.get("temporal") or {},
        "productivity_explainability": {
            "available": ((raw.get("productivity_explainability") or {}).get("available")),
            "top_feature_counts": ((raw.get("productivity_explainability") or {}).get("top_feature_counts") or {}),
            "top_factors_preview": ((raw.get("productivity_explainability") or {}).get("top_factors_preview") or []),
            "counterfactuals_preview": ((raw.get("productivity_explainability") or {}).get("counterfactuals_preview") or []),
            "animal_explainability": ((raw.get("productivity_explainability") or {}).get("animal_explainability") or []),
        },
        "mastitis_risk": {
            "available": ((raw.get("mastitis_risk") or {}).get("available")),
        },
        "playbooks": {
            "recommended": [
                {
                    "target_kind": p.get("target_kind"),
                    "target_type": p.get("target_type"),
                    "title": p.get("title"),
                }
                for p in recommended
            ]
        },
    }


def _build_snapshot_from_artifacts(
    *,
    project_root: Path,
    artifacts_root: Path,
    web_storage_dir: Path,
    scenario: ScenarioSpec,
    snapshot_dir: Path,
) -> None:
    base = artifacts_root / scenario.data_version
    qc_dir = base / "qc" / scenario.qc_run
    score_dir = base / "scoring" / scenario.scoring_run
    report_dir = base / "reports" / scenario.report_version
    decisions_dir = base / "decisions"

    scored_latest = pd.read_csv(score_dir / "scored_latest.csv")
    fact_pack_path = report_dir / "fact_pack.json"
    report_summary_path = report_dir / "report_summary.json"
    qc_summary_path = qc_dir / "qc_summary.json"
    scoring_summary_path = score_dir / "scoring_summary.json"

    narrative = generate_report_text_fallback(_read_json(fact_pack_path))
    first_object_id = str(scored_latest.iloc[0]["animal_id"]) if not scored_latest.empty else "NA"
    _db_path, tasks_rows, audit_rows = _seed_web_state(
        project_root=project_root,
        web_storage_dir=web_storage_dir,
        scenario=scenario,
        first_object_id=first_object_id,
    )

    snapshot_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        snapshot_dir / "lineage.json",
        {
            "scenario": scenario.name,
            "description": scenario.description,
            "versions": {
                "data_version": scenario.data_version,
                "qc_run": scenario.qc_run,
                "model_version": scenario.model_version,
                "scoring_run": scenario.scoring_run,
                "report_version": scenario.report_version,
            },
        },
    )
    _write_json(
        snapshot_dir / "artifact_presence.json",
        {
            "qc_report_xlsx": (qc_dir / "qc_report.xlsx").exists(),
            "scored_latest_csv": (score_dir / "scored_latest.csv").exists(),
            "recommendations_xlsx": (score_dir / "exports" / "recommendations.xlsx").exists(),
            "fact_pack_json": fact_pack_path.exists(),
            "report_summary_json": report_summary_path.exists(),
            "report_docx": (report_dir / "exports" / "report.docx").exists(),
            "decision_log_csv": (decisions_dir / "decision_log.csv").exists(),
            "decision_log_xlsx": (decisions_dir / "decision_log.xlsx").exists(),
            "decision_log_jsonl": (decisions_dir / "decision_log.jsonl").exists(),
            "web_db": (web_storage_dir / "web.db").exists(),
        },
    )
    _write_json(snapshot_dir / "qc_summary.json", _normalize_qc_summary(qc_summary_path))
    _write_json(snapshot_dir / "scoring_summary.json", _normalize_scoring_summary(scoring_summary_path))
    _write_json(snapshot_dir / "fact_pack.json", _normalize_fact_pack(fact_pack_path))
    _write_json(snapshot_dir / "report_summary.json", _normalize_report_summary(report_summary_path))
    _write_json(snapshot_dir / "report_narrative.json", narrative)

    score_rows = _normalize_dataframe(
        scored_latest,
        columns=[
            "farm_id",
            "animal_id",
            "ear_tag",
            "lactation_no",
            "calving_date",
            "milk_305d_kg",
            "y_pred",
            "residual",
            "index_in_group",
            "rank_in_group",
            "rank_in_farm",
            "group_size",
            "confidence",
            "action",
            "action_reasons",
        ],
        sort_by=["farm_id", "animal_id", "lactation_no"],
    )
    _write_csv(
        snapshot_dir / "scored_latest.csv",
        score_rows,
        [
            "farm_id",
            "animal_id",
            "ear_tag",
            "lactation_no",
            "calving_date",
            "milk_305d_kg",
            "y_pred",
            "residual",
            "index_in_group",
            "rank_in_group",
            "rank_in_farm",
            "group_size",
            "confidence",
            "action",
            "action_reasons",
        ],
    )

    decisions = pd.read_csv(decisions_dir / "decision_log.csv")
    decision_rows = _normalize_dataframe(
        decisions,
        columns=["user", "animal_id", "lactation_id", "recommendation_type", "decision", "comment", "lactation_no", "farm_id", "scoring_run"],
        sort_by=["animal_id", "lactation_id", "recommendation_type"],
    )
    _write_csv(
        snapshot_dir / "decision_log.csv",
        decision_rows,
        ["user", "animal_id", "lactation_id", "recommendation_type", "decision", "comment", "lactation_no", "farm_id", "scoring_run"],
    )
    _write_json(snapshot_dir / "tasks.json", _normalize_tasks(tasks_rows))
    _write_json(snapshot_dir / "audit.json", _normalize_audit(audit_rows))


def generate_scenario_snapshot(
    *,
    project_root: Path,
    golden_root: Path,
    scenario_name: str,
    snapshot_dir: Path,
    work_dir: Path,
) -> None:
    scenario = get_scenario_spec(scenario_name)
    inputs_dir = golden_root / "scenarios" / scenario_name / "inputs" / "external"
    if not inputs_dir.exists():
        raise FileNotFoundError(f"golden inputs not found: {inputs_dir}")

    artifacts_root = work_dir / "artifacts"
    web_storage_dir = work_dir / "web_storage"
    artifacts_root.mkdir(parents=True, exist_ok=True)

    contracts = load_contracts_dir(project_root / "configs" / "contracts")
    dataset_specs = [
        ("farms", "dm_farms", "farms_ext.csv", "farms_example.yaml"),
        ("animals", "dm_animals", "animals_ext.csv", "animals_example.yaml"),
        ("lactations", "dm_lactations", "lactations_ext.csv", "lactations_example.yaml"),
    ]
    for dataset_key, contract_key, file_name, mapping_name in dataset_specs:
        ingest_dataset(
            dataset_key=dataset_key,
            file_path=inputs_dir / file_name,
            mapping_path=project_root / "configs" / "mappings" / mapping_name,
            contract=contracts[contract_key],
            artifacts_root=artifacts_root,
            out_version=scenario.data_version,
        )

    qc = run_qc(
        data_version=scenario.data_version,
        artifacts_root=artifacts_root,
        contracts_dir=project_root / "configs" / "contracts",
        qc_run=scenario.qc_run,
    )
    if str(qc.get("qc_status")) != scenario.expected_qc_status:
        raise RuntimeError(
            f"scenario {scenario.name}: expected qc_status={scenario.expected_qc_status}, got {qc.get('qc_status')}"
        )

    train = train_productivity_model(
        artifacts_root=artifacts_root,
        data_version=scenario.data_version,
        qc_run=scenario.qc_run,
        model_version=scenario.model_version,
    )
    if not train.get("ok"):
        raise RuntimeError(f"scenario {scenario.name}: train failed: {train}")

    score = run_scoring(
        artifacts_root=artifacts_root,
        data_version=scenario.data_version,
        model_version=scenario.model_version,
        scoring_run=scenario.scoring_run,
    )
    if not score.get("ok"):
        raise RuntimeError(f"scenario {scenario.name}: score failed: {score}")

    report = run_report(
        artifacts_root=artifacts_root,
        data_version=scenario.data_version,
        qc_run=scenario.qc_run,
        model_version=scenario.model_version,
        scoring_run=scenario.scoring_run,
        mode="fallback",
        report_version=scenario.report_version,
        make_pdf=False,
        llm_model=None,
    )
    if not report.get("ok"):
        raise RuntimeError(f"scenario {scenario.name}: report failed: {report}")

    init_decision_log(
        artifacts_root=artifacts_root,
        data_version=scenario.data_version,
        scoring_run=scenario.scoring_run,
        user="verify_refactor",
        template_from_scoring=True,
    )

    _build_snapshot_from_artifacts(
        project_root=project_root,
        artifacts_root=artifacts_root,
        web_storage_dir=web_storage_dir,
        scenario=scenario,
        snapshot_dir=snapshot_dir,
    )


def _build_golden_manifest(*, golden_root: Path, scenario_names: Iterable[str] | None = None) -> dict[str, Any]:
    scenarios_payload: list[dict[str, Any]] = []
    total_bytes = 0
    for scenario in resolve_scenario_specs(scenario_names):
        scenario_name = scenario.name
        scenario_root = golden_root / "scenarios" / scenario_name
        inputs_root = scenario_root / "inputs"
        snapshot_root = scenario_root / "snapshot"
        input_files = _snapshot_file_index(inputs_root)
        snapshot_files = _snapshot_file_index(snapshot_root)
        scenario_total = _manifest_total_bytes(input_files) + _manifest_total_bytes(snapshot_files)
        total_bytes += scenario_total
        scenarios_payload.append(
            {
                "scenario": scenario_name,
                "description": scenario.description,
                "expected_qc_status": scenario.expected_qc_status,
                "versions": {
                    "data_version": scenario.data_version,
                    "qc_run": scenario.qc_run,
                    "model_version": scenario.model_version,
                    "scoring_run": scenario.scoring_run,
                    "report_version": scenario.report_version,
                },
                "inputs": {
                    "root": f"scenarios/{scenario_name}/inputs",
                    "file_count": len(input_files),
                    "total_bytes": _manifest_total_bytes(input_files),
                    "files": input_files,
                },
                "snapshot": {
                    "root": f"scenarios/{scenario_name}/snapshot",
                    "file_count": len(snapshot_files),
                    "total_bytes": _manifest_total_bytes(snapshot_files),
                    "files": snapshot_files,
                },
                "scenario_total_bytes": scenario_total,
            }
        )
    return {
        "schema": "genomeai.golden_manifest.v1",
        "generated_at_utc": _utc_now_iso(),
        "golden_root": str(golden_root.resolve()),
        "scenario_count": len(scenarios_payload),
        "total_bytes": total_bytes,
        "scenarios": scenarios_payload,
    }


def _write_golden_manifest(*, golden_root: Path, scenario_names: Iterable[str] | None = None) -> Path:
    manifest = _build_golden_manifest(golden_root=golden_root, scenario_names=scenario_names)
    manifest_path = golden_manifest_path(golden_root)
    _write_json(manifest_path, manifest)
    return manifest_path


def _validate_golden_manifest(*, golden_root: Path, scenario_names: Iterable[str] | None = None) -> list[FileDiff]:
    selected = select_scenario_names(scenario_names)
    manifest_path = golden_manifest_path(golden_root)
    diffs: list[FileDiff] = []
    if not manifest_path.exists():
        return [FileDiff(file="manifest.json", kind="missing", detail="В golden отсутствует manifest.json. Пересоберите golden вручную через --update-golden.")]
    raw = _read_json(manifest_path)
    if raw.get("schema") != "genomeai.golden_manifest.v1":
        diffs.append(FileDiff(file="manifest.json", kind="content", detail=f"Неверная schema в manifest.json: {raw.get('schema')!r}"))
        return diffs
    manifest_scenarios = {item.get("scenario"): item for item in (raw.get("scenarios") or [])}
    for scenario_name in selected:
        scenario_entry = manifest_scenarios.get(scenario_name)
        if not scenario_entry:
            diffs.append(FileDiff(file="manifest.json", kind="missing", detail=f"В manifest.json отсутствует сценарий {scenario_name}."))
            continue
        for section_key, root_suffix in (("inputs", "inputs"), ("snapshot", "snapshot")):
            section = scenario_entry.get(section_key) or {}
            files = section.get("files") or []
            root = golden_root / "scenarios" / scenario_name / root_suffix
            actual_index = {item["path"]: item for item in _snapshot_file_index(root)}
            manifest_index = {item.get("path"): item for item in files}
            missing = sorted(set(manifest_index) - set(actual_index))
            extra = sorted(set(actual_index) - set(manifest_index))
            for rel in missing:
                diffs.append(FileDiff(file=f"scenarios/{scenario_name}/{root_suffix}/{rel}", kind="missing", detail=f"Файл есть в manifest.json, но отсутствует на диске ({section_key})."))
            for rel in extra:
                diffs.append(FileDiff(file=f"scenarios/{scenario_name}/{root_suffix}/{rel}", kind="extra", detail=f"Файл есть на диске, но отсутствует в manifest.json ({section_key})."))
            for rel in sorted(set(actual_index) & set(manifest_index)):
                actual = actual_index[rel]
                expected = manifest_index[rel]
                expected_hash = expected.get("sha256")
                actual_hash = actual.get("sha256")
                expected_size = int(expected.get("size_bytes") or 0)
                actual_size = int(actual.get("size_bytes") or 0)
                if expected_hash != actual_hash or expected_size != actual_size:
                    diffs.append(
                        FileDiff(
                            file=f"scenarios/{scenario_name}/{root_suffix}/{rel}",
                            kind="content",
                            detail=(
                                f"Manifest mismatch: sha256 {expected_hash} -> {actual_hash}; "
                                f"size_bytes {expected_size} -> {actual_size}"
                            ),
                        )
                    )
    return diffs


def verify_refactor(
    *,
    project_root: Path,
    golden_root: Path,
    scenario_names: Iterable[str] | None = None,
    report_root: Path | None = None,
) -> dict[str, Any]:
    ensure_golden_inputs(golden_root=golden_root, project_root=project_root)
    selected = [scenario.name for scenario in resolve_scenario_specs(scenario_names)]

    created_at = _utc_now_iso()
    rr = resolve_verify_report_root(project_root=project_root, report_root=report_root)
    rr.mkdir(parents=True, exist_ok=True)

    scenario_reports: list[ScenarioReport] = []
    manifest_diffs = _validate_golden_manifest(golden_root=golden_root, scenario_names=selected)
    if manifest_diffs:
        scenario_reports.append(
            ScenarioReport(
                scenario="golden_manifest",
                ok=False,
                compared_files=0,
                differences=manifest_diffs,
                expected_snapshot=str((golden_root / "manifest.json").resolve()),
                actual_snapshot=str(golden_root.resolve()),
            )
        )
    for scenario_name in selected:
        expected_snapshot = golden_root / "scenarios" / scenario_name / "snapshot"
        with tempfile.TemporaryDirectory(prefix=f"verify_refactor_{scenario_name}_") as tmp:
            work_dir = Path(tmp)
            actual_snapshot = rr / "snapshots" / scenario_name
            generate_scenario_snapshot(
                project_root=project_root,
                golden_root=golden_root,
                scenario_name=scenario_name,
                snapshot_dir=actual_snapshot,
                work_dir=work_dir,
            )
            scenario_reports.append(compare_snapshot_dirs(expected_snapshot, actual_snapshot))

    report = VerifyReport(
        schema="genomeai.verify_refactor_report.v1",
        created_at_utc=created_at,
        golden_root=str(golden_root.resolve()),
        ok=all(s.ok for s in scenario_reports),
        scenarios=scenario_reports,
    )
    json_path = rr / "verify_report.json"
    md_path = rr / "verify_report.md"
    _write_json(json_path, verify_report_payload(report))
    _write_text(md_path, render_markdown(report))
    return {
        "ok": report.ok,
        "report_json": str(json_path.resolve()),
        "report_md": str(md_path.resolve()),
        "report_root": str(rr.resolve()),
        "golden_manifest": str(golden_manifest_path(golden_root).resolve()),
        "scenarios": [
            {
                "scenario": s.scenario,
                "ok": s.ok,
                "differences": len(s.differences),
                "compared_files": s.compared_files,
            }
            for s in report.scenarios
        ],
    }


def update_golden(
    *,
    project_root: Path,
    golden_root: Path,
    scenario_names: Iterable[str] | None = None,
) -> dict[str, Any]:
    ensure_golden_inputs(golden_root=golden_root, project_root=project_root)
    selected = [scenario.name for scenario in resolve_scenario_specs(scenario_names)]
    updated: list[str] = []
    for scenario_name in selected:
        snapshot_dir = golden_root / "scenarios" / scenario_name / "snapshot"
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        with tempfile.TemporaryDirectory(prefix=f"update_golden_{scenario_name}_") as tmp:
            generate_scenario_snapshot(
                project_root=project_root,
                golden_root=golden_root,
                scenario_name=scenario_name,
                snapshot_dir=snapshot_dir,
                work_dir=Path(tmp),
            )
        updated.append(scenario_name)
    manifest_path = _write_golden_manifest(golden_root=golden_root, scenario_names=selected)
    return {
        "ok": True,
        "updated_scenarios": updated,
        "golden_root": str(golden_root.resolve()),
        "manifest_path": str(manifest_path.resolve()),
    }

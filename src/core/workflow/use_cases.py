from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from core.workflow.alerts import AlertCreate


AlertCandidate = Mapping[str, Any]


def alert_candidate_to_create(candidate: AlertCandidate) -> AlertCreate:
    """Convert offline alert candidate dict into workflow AlertCreate.

    Keeps adapter payload parsing in one place so UI/API callers don't duplicate it.
    """

    return AlertCreate(
        alert_type=str(candidate["alert_type"]),
        title=str(candidate["title"]),
        source=str(candidate["source"]),
        cause=str(candidate["cause"]),
        confidence=(float(candidate["confidence"]) if candidate.get("confidence") is not None else None),
        object_type=str(candidate["object_type"]),
        object_id=str(candidate["object_id"]),
        deadline=(str(candidate["deadline"]) if candidate.get("deadline") else None),
        owner_user_id=(int(candidate["owner_user_id"]) if candidate.get("owner_user_id") is not None else None),
        attachments=list(candidate.get("attachments") or []),
        why=dict(candidate.get("why") or {}),
        what_to_do=list(candidate.get("what_to_do") or []),
        data_version=(str(candidate["data_version"]) if candidate.get("data_version") else None),
        qc_run=(str(candidate["qc_run"]) if candidate.get("qc_run") else None),
        model_version=(str(candidate["model_version"]) if candidate.get("model_version") else None),
        scoring_run=(str(candidate["scoring_run"]) if candidate.get("scoring_run") else None),
        report_version=(str(candidate["report_version"]) if candidate.get("report_version") else None),
        dedupe_key=(str(candidate["dedupe_key"]) if candidate.get("dedupe_key") else None),
    )


def generate_alerts_and_tasks_use_case(
    *,
    conn,
    tenant_id: str,
    data_version: str,
    artifacts_root: Path,
    catalog_path: Path,
    generate_alert_candidates: Callable[..., Iterable[AlertCandidate]],
    load_tasks_catalog: Callable[[Path], dict[str, Any]],
    upsert_generated_alerts: Callable[..., tuple[int, int]],
    auto_create_tasks_from_alerts: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Generate alerts from offline-core facts and auto-create eligible tasks.

    This use case centralizes the orchestration shared by API and Streamlit Action Center.
    Audit remains the responsibility of adapters.
    """

    dv = str(data_version)
    root = Path(artifacts_root).resolve()
    catalog_file = Path(catalog_path).resolve()

    candidates = list(generate_alert_candidates(artifacts_root=root, data_version=dv) or [])
    alerts = [alert_candidate_to_create(candidate) for candidate in candidates]
    inserted, updated = upsert_generated_alerts(conn, tenant_id=str(tenant_id), alerts=alerts)

    catalog = load_tasks_catalog(catalog_file)
    auto_tasks = auto_create_tasks_from_alerts(
        conn,
        tenant_id=str(tenant_id),
        catalog=catalog,
        data_version=dv,
    )

    return {
        "candidates": int(len(candidates)),
        "inserted": int(inserted),
        "updated": int(updated),
        "auto_tasks": auto_tasks,
    }

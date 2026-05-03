from __future__ import annotations

from pathlib import Path

from core.workflow.alerts import upsert_generated_alerts
from core.workflow.tasks import auto_create_tasks_from_alerts, load_tasks_catalog
from core.workflow.use_cases import generate_alerts_and_tasks_use_case


def generate_alerts_and_tasks(
    *,
    conn,
    tenant_id: str,
    data_version: str,
    artifacts_root: Path,
    project_root: Path,
) -> dict[str, object]:
    """Canonical workflow entrypoint for Action Center generation in API/UI."""

    from genomeai.alerts_v2 import generate_alerts_v2

    return generate_alerts_and_tasks_use_case(
        conn=conn,
        tenant_id=tenant_id,
        data_version=data_version,
        artifacts_root=Path(artifacts_root),
        catalog_path=Path(project_root) / "configs" / "tasks_v1" / "catalog.yaml",
        generate_alert_candidates=generate_alerts_v2,
        load_tasks_catalog=load_tasks_catalog,
        upsert_generated_alerts=upsert_generated_alerts,
        auto_create_tasks_from_alerts=auto_create_tasks_from_alerts,
    )

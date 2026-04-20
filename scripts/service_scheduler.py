from __future__ import annotations

import os

from core.infra.web_db import connect, init_db, get_settings
from web_cabinet.connectors_v1 import schedule_due_connector_jobs
from scripts.service_runtime import run_loop

settings = get_settings()


def tick() -> dict[str, object]:
    if str(getattr(settings, "runtime_storage_backend", "")).lower() == "postgres":
        return {
            "scheduled_jobs": 0,
            "matched_bindings": 0,
            "scheduler_mode": "postgres_cutover_gap_noop",
        }

    conn = connect(settings.db_path)
    try:
        init_db(conn)
        result = schedule_due_connector_jobs(conn=conn, tenant_id=os.environ.get("GENOMEAI_TENANT_ID", "default"), actor_username="system.scheduler", actor_role="system")
        return {
            "scheduled_jobs": int(result.get("jobs_enqueued") or 0),
            "matched_bindings": int(result.get("bindings_matched") or 0),
        }
    finally:
        conn.close()


if __name__ == "__main__":
    run_loop(
        component="scheduler",
        interval_sec=float(os.environ.get("GENOMEAI_SCHEDULER_INTERVAL_SEC", "30")),
        heartbeat_path=os.environ.get("GENOMEAI_SCHEDULER_HEARTBEAT", "/tmp/genomeai-scheduler-heartbeat.json"),
        tick=tick,
    )

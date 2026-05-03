-- Adult contour maintenance checks for backup / restore / support bundle posture.
-- Run against PostgreSQL runtime state, not legacy sqlite.

-- 1) Schema revision / runtime state overview
SELECT current_database() AS db_name, current_user AS db_user, now() AT TIME ZONE 'UTC' AS checked_at_utc;

-- 2) Runtime entities row counts
SELECT 'auth_users' AS entity, COUNT(*) AS row_count FROM auth_users
UNION ALL SELECT 'auth_sessions', COUNT(*) FROM auth_sessions
UNION ALL SELECT 'jobs', COUNT(*) FROM jobs
UNION ALL SELECT 'audit_log', COUNT(*) FROM audit_log
UNION ALL SELECT 'alerts_v2', COUNT(*) FROM alerts_v2
UNION ALL SELECT 'tasks_v1', COUNT(*) FROM tasks_v1
UNION ALL SELECT 'decision_log_v2', COUNT(*) FROM decision_log_v2
UNION ALL SELECT 'connector_runs', COUNT(*) FROM connector_runs;

-- 3) Recent operational lineage
SELECT id, public_job_id, status, queue_name, run_id, data_version, created_at
FROM jobs
ORDER BY id DESC
LIMIT 20;

-- 4) Recent privileged / maintenance audit
SELECT id, action, status, ts, object_id
FROM audit_log
WHERE action IN ('backup.create', 'backup.restore', 'artifact.support_bundle', 'backup.cleanup', 'backup.drill')
ORDER BY id DESC
LIMIT 20;

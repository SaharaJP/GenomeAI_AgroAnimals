-- T34-03 runtime state operational checks (PostgreSQL)
-- Run in adult/stage contour against the runtime PostgreSQL database.

-- entity counts
SELECT 'jobs' AS entity, COUNT(*) AS row_count FROM jobs
UNION ALL SELECT 'audit_log', COUNT(*) FROM audit_log
UNION ALL SELECT 'alerts_v2', COUNT(*) FROM alerts_v2
UNION ALL SELECT 'tasks_v1', COUNT(*) FROM tasks_v1
UNION ALL SELECT 'decision_log_v2', COUNT(*) FROM decision_log_v2
UNION ALL SELECT 'connector_runs', COUNT(*) FROM connector_runs
UNION ALL SELECT 'saved_views_v1', COUNT(*) FROM saved_views_v1
UNION ALL SELECT 'favorites_v1', COUNT(*) FROM favorites_v1
UNION ALL SELECT 'report_templates_v1', COUNT(*) FROM report_templates_v1
UNION ALL SELECT 'report_approvals_v1', COUNT(*) FROM report_approvals_v1
UNION ALL SELECT 'whatif_scenarios_v1', COUNT(*) FROM whatif_scenarios_v1
UNION ALL SELECT 'whatif_reports_v1', COUNT(*) FROM whatif_reports_v1
ORDER BY entity;

-- jobs lineage sanity
SELECT COUNT(*) AS jobs_missing_lineage
FROM jobs
WHERE status IN ('running','success','failed','cancelled')
  AND COALESCE(run_id, '') = ''
  AND COALESCE(data_version, '') = '';

-- task/decision linkage sanity
SELECT COUNT(*) AS tasks_linked_to_missing_decision
FROM tasks_v1 t
LEFT JOIN decision_log_v2 d
  ON d.tenant_id = t.tenant_id AND d.decision_id = t.linked_decision_id
WHERE COALESCE(t.linked_decision_id, '') <> ''
  AND d.decision_id IS NULL;

-- alert/decision linkage sanity
SELECT COUNT(*) AS decisions_linked_to_missing_alert
FROM decision_log_v2 d
LEFT JOIN alerts_v2 a
  ON a.tenant_id = d.tenant_id AND a.alert_id = d.related_alert
WHERE COALESCE(d.related_alert, '') <> ''
  AND a.alert_id IS NULL;

-- retention-oriented operational windows
SELECT status, COUNT(*) AS cnt
FROM connector_runs
GROUP BY status
ORDER BY status;

SELECT tenant_id, status, COUNT(*) AS cnt
FROM report_approvals_v1
GROUP BY tenant_id, status
ORDER BY tenant_id, status;

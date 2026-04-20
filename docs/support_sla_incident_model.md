# Support / SLA / incident model

T31-03 adds a **runnable support operating contour** rather than a text-only policy.

## What is included

- severity levels with explicit response targets and escalation paths;
- support case intake;
- critical incident intake;
- known issues with release-note linkage;
- support bundle usage and diagnostics linkage;
- exportable JSON / Markdown reports.

## Runtime contour

- Starter records live in `data/support/support_operating_records_v1.json` and are marked as sample-only.
- Runtime changes are written to `web_storage/support/support_operating_records_v1.json`.
- Admin observability can surface `support_sla_incident_report.json` as a diagnostics report.

## Guardrails

- Response targets are **operating targets**, not unsupported contractual SLA promises.
- Critical incidents must preserve traceable linkage to diagnostics, support bundle usage and version context.
- Known issues and release-note linkage are part of customer-safe support communication.

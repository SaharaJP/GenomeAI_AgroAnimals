# Production operability / supportability / maintainability

T34-09 формализует эксплуатационный контур как часть кода и конфигурации, а не только markdown.

## Что добавлено
- metrics contract с обязательными correlation ids и runtime labels;
- release checklist и rollback checklist как machine-readable config;
- incident-first troubleshooting flow и operator/admin checklists как config;
- production operability report и operability endpoints;
- docs-to-code consistency check и CI gate расширение.

## Базовые surfaces
- `GET /api/operability`
- `GET /api/metrics-contract`
- `GET /admin/operability`
- `python scripts/check_production_operability.py`
- `python scripts/check_docs_to_code_consistency.py`

## Guardrails
- observability не считается достаточной, если есть только логи без correlation ids и labels;
- release/rollback не считаются формализованными без checklist + evidence requirements;
- supportability не считается достаточной без support bundle expectations и incident-first flow.

# T15-10 — Security/RBAC + Audit централизованы в core

Что сделано:
- RBAC policy/permissions/roles перенесены в `src/core/security/policy.py`.
- Матрица прав и её валидация перенесены в `src/core/security/matrix.py`.
- Audit events/filters/retention перенесены в `src/core/audit/events.py`.
- `web_cabinet.rbac`, `web_cabinet.audit`, `web_cabinet.security_matrix` оставлены как shim-модули с deprecation warning.
- FastAPI guard и Streamlit guard теперь используют общий core-механизм проверки прав.
- Добавлены negative tests на запреты и тесты на единый поиск/фильтры audit.

Проверка:
- targeted pytest по core/web/streamlit security+audit
- `python -m web_cabinet.smoke --workdir _tmp/t15_10_smoke --clean`
- `python -m genomeai.cli verify_refactor --project-root . --golden golden --report-root artifacts/_verify_refactor_t15_10`

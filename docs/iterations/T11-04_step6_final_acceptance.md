# T11-04 — What‑If 2.0 (FINAL)

## Цель
Закрыть acceptance criteria T11-04: пользователь создаёт/сохраняет сценарий, сравнивает 2–3 сценария с базой, генерирует PDF отчёт; директор утверждает сценарий; audit фиксирует действия.

## Что покрыто
- **Сценарии**: create/list/get/update/approve/clone/archive (web.db: `whatif_scenarios_v1`).
- **Сравнение**: 2–3 сценария + BASE (API: `POST /api/whatif_compare_v1`).
- **Отчёт**: PDF по сценарию (API: `POST /api/whatif_scenarios_v1/{scenario_id}/report_pdf`, web.db: `whatif_reports_v1`).
- **RBAC**: права на создание/утверждение/отчёты/clone/archive.
- **Audit**: `whatif_scenario.create/update/approve/clone/archive/compare/run`, `whatif_report.generate`.

## Быстрый E2E
Запуск теста (создание 2 сценариев → approve одного → compare → report → audit):

```bash
pytest -q tests/web/test_t11_04_e2e_flow.py
```

## Основные эндпоинты
- `GET /api/whatif_scenarios_v1`
- `POST /api/whatif_scenarios_v1`
- `POST /api/whatif_scenarios_v1/{id}/update`
- `POST /api/whatif_scenarios_v1/{id}/approve`
- `POST /api/whatif_scenarios_v1/{id}/clone`
- `POST /api/whatif_scenarios_v1/{id}/archive`
- `POST /api/whatif_compare_v1`
- `GET /api/whatif_reports_v1?scenario_id=...`
- `POST /api/whatif_scenarios_v1/{id}/report_pdf`


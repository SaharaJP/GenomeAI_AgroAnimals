# T11-04 Step1 — What-If 2.0: сохранение сценариев (draft/approved) + RBAC + audit

Цель шага: добавить базовую модель **saved scenarios** для what-if, чтобы пользователь мог сохранить набор параметров, а директор — утвердить сценарий.

Что сделано:
1) Добавлена таблица `whatif_scenarios_v1` в `web.db` (idempotent init).
2) Добавлены permissions (RBAC):
   - `whatif.scenarios.view`
   - `whatif.scenarios.write`
   - `whatif.scenarios.approve`
3) Реализованы CRUD-операции сценариев (draft) и approve.
4) Добавлены API эндпоинты (FastAPI):
   - `GET /api/whatif_scenarios_v1`
   - `POST /api/whatif_scenarios_v1`
   - `GET /api/whatif_scenarios_v1/{scenario_id}`
   - `POST /api/whatif_scenarios_v1/{scenario_id}/update`
   - `POST /api/whatif_scenarios_v1/{scenario_id}/approve`
5) Добавлена интеграция в Streamlit страницу `9_Economics_WhatIf.py`:
   - список сценариев
   - сохранение сценария
   - применение параметров сценария
   - approve (для ролей с `whatif.scenarios.approve`)
6) Все критичные действия пишутся в audit log (`whatif_scenario.create/update/approve`).

Проверка:
```bash
# Web cabinet API tests
pytest -q tests/web/test_whatif_scenarios_v1.py

# Streamlit UI
streamlit run streamlit_app/app.py
# откройте страницу "Экономика / What-if (T7-01)" и сохраните сценарий, затем зайдите под director/director и утвердите.
```

Ограничения шага:
- Сценарий пока хранит только **мультипликаторы** economics_whatif + контекст (dv/date/cfg).
- Сравнение 2–3 сценариев и PDF-отчет будут добавлены на следующих шагах T11-04.

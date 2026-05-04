# Test Baseline — Week 2–5 Fix Queue

**Date:** 2026-05-04  
**Snapshot:** `/tmp/pytest_baseline.log`  
**Result:** 607 collected, 114 collection errors → **0 tests ran** (interrupted at collection)

All errors occur at **import time**, before any test executes.  
No runtime failures (DB, Redis, env) were observed — collection was aborted first.

---

## Summary

| # | Категория | Файлов | Root cause |
|---|-----------|-------:|------------|
| A | `streamlit_app` модуль отсутствует | 63 | Пакет `streamlit_app` не установлен и не существует в репо |
| B | `init_db` удалён из `web_cabinet.db` | 18 | SQLite→Postgres миграция T34-09 удалила legacy API |
| C | `init_db` удалён из `core.infra.web_db` | 21 | То же, но импорт через канонический модуль |
| D | `connect` удалён из `web_cabinet.db` | 7 | То же, дополнительно нужна функция `connect` |
| E | `connect` удалён из `core.infra.web_db` | 1 | То же + `create_user_v2`, `get_user_v2_any_by_*` |
| F | Каскад через `core.interoperability` | 3 | `migration_verification.py:15` импортирует `init_db` |
| G | `collect_streamlit_contract` отсутствует | 1 | Функция не добавлена в `core.public_interfaces` |
| | **Итого** | **114** | |

---

## Категория A — `ModuleNotFoundError: No module named 'streamlit_app'` (63 файла)

**Причина:** Пакет `streamlit_app` (legacy Streamlit-фронтенд) не существует в репо и не установлен.  
**Лечение:** Все эти тесты заточены под Streamlit-слой, который был заменён на `web_app/` (Next.js). Нужно решить: удалить тесты, переписать под `web_cabinet` / `core.*`, либо создать stub-модуль.

| Файл теста | Импортируемый модуль `streamlit_app.*` |
|---|---|
| `tests/test_t10_01_glossary_kpis_present.py` | `glossary_v3` |
| `tests/test_t10_01_glossary_v3.py` | `glossary_v3` |
| `tests/test_t10_01_home_pages_by_role.py` | `ia_v3` |
| `tests/test_t10_01_ia_v3.py` | `ia_v3` |
| `tests/test_t10_03_nav_utils.py` | `nav_utils` |
| `tests/test_t10_03_report_nav_utils.py` | `nav_utils` |
| `tests/test_t10_04_favorites_role_filter.py` | `personalization` |
| `tests/test_t10_04_saved_views_state.py` | `saved_views_state` |
| `tests/test_t14_04_explainability_step2.py` | `mastitis_ui_utils` |
| `tests/test_t14_04_explainability_step3.py` | `mastitis_ui_utils` |
| `tests/test_t14_04_explainability_step4.py` | `mastitis_ui_utils` |
| `tests/test_t15_05_job_runner.py` | `pipeline_jobs` |
| `tests/test_t15_07_ml_interface_parity_step5.py` | `pipeline_jobs` |
| `tests/test_t15_10_streamlit_security_shared.py` | `common` |
| `tests/test_t18_01_unified_shell.py` | `unified_shell` |
| `tests/test_t18_02_auth_bridge.py` | `auth_bridge` |
| `tests/test_t18_02_common_auth_integration.py` | `common` |
| `tests/test_t18_03_jobs_center.py` | `auth_bridge` |
| `tests/test_t18_04_upload_ingest.py` | `upload_ingest` |
| `tests/test_t18_05_pipeline_ops.py` | `pipeline_jobs` |
| `tests/test_t18_06_workflow_pack.py` | `auth_bridge` |
| `tests/test_t18_07_admin_console.py` | `admin_console` |
| `tests/test_t18_08_platform_pages.py` | `auth_bridge` |
| `tests/test_t18_09_streamlit_parity_gates.py` | `parity_smoke` |
| `tests/test_t19_01_streamlit_ia_navigation.py` | `navigation_ux` |
| `tests/test_t19_02_home_pages.py` | `home_widgets` |
| `tests/test_t19_03_upload_ingest_ux.py` | `upload_ingest` |
| `tests/test_t19_04_qc_workspace.py` | `qc_workspace` |
| `tests/test_t19_05_model_ops_workspace.py` | `model_ops_workspace` |
| `tests/test_t19_06_jobs_workspace.py` | `auth_bridge` |
| `tests/test_t19_07_action_flow_ux.py` | `action_flow_ux` |
| `tests/test_t19_08_profiles_ux.py` | `profiles_ux` |
| `tests/test_t19_09_reports_ux.py` | `reports_ux` |
| `tests/test_t19_10_economics_ux.py` | `economics_ux` |
| `tests/test_t19_11_admin_console_ux.py` | `admin_console` |
| `tests/test_t19_12_assistant_feedback_ux.py` | `assistant_feedback_ux` |
| `tests/test_t19_13_design_system.py` | `design_system` |
| `tests/test_t19_14_streamlit_final_gates.py` | `parity_smoke` |
| `tests/test_t20_04_animal_profile_daily_use.py` | `animal_profile_daily_use` |
| `tests/test_t20_05_group_profile_operational_hub.py` | `group_profile_operational_hub` |
| `tests/test_t21_05_worklist_saved_views.py` | `personalization` |
| `tests/test_t22_01_reproduction_state_machine.py` | `animal_profile_daily_use` |
| `tests/test_t22_03_reproduction_cockpit.py` | `reproduction_cockpit` |
| `tests/test_t22_04_calving_forecast_and_inventory.py` | `calving_forecast` |
| `tests/test_t22_05_repro_mating_integration.py` | `repro_mating_integration` |
| `tests/test_t23_01_vet_protocol_engine.py` | `vet_protocol_engine` |
| `tests/test_t23_02_treatment_journal_withdrawal.py` | `treatment_journal_withdrawal` |
| `tests/test_t23_04_drug_use_compliance.py` | `drug_use_compliance` |
| `tests/test_t24_01_universal_list_builder.py` | `saved_views_state` |
| `tests/test_t24_02_operational_report_builder.py` | `saved_views_state` |
| `tests/test_t24_04_trend_reports_compare_periods.py` | `trend_reports_compare_periods` |
| `tests/test_t24_05_report_to_action_bridge.py` | `auth_bridge` |
| `tests/test_t25_01_mobile_shell_pwa_foundation.py` | `mobile_shell_pwa` |
| `tests/test_t25_04_field_friendly_ui_patterns.py` | `field_friendly_ui` |
| `tests/test_t28_01_multi_site_operational_model.py` | `saved_views_state` |
| `tests/test_t28_03_enterprise_benchmark_views.py` | `enterprise_benchmark_views` |
| `tests/test_t28_05_operational_sla_and_gates.py` | `admin_console` |
| `tests/test_t29_01_embedded_operational_assistant.py` | `assistant_feedback_ux` |
| `tests/test_t29_03_feedback_calibration_loop_v2.py` | `feedback_capture_v2` |
| `tests/test_t30_01_competitive_acceptance_set.py` | `admin_console` |
| `tests/test_t30_02_training_onboarding_by_role.py` | `unified_shell` |
| `tests/test_t30_03_demo_farm_and_benchmark_demos.py` | `unified_shell` |
| `tests/test_t30_04_commercial_packaging_and_editions.py` | `ia_v3` |

---

## Категория B — `ImportError: cannot import name 'init_db' from 'web_cabinet.db'` (18 файлов)

**Причина:** T34-09 (SQLite→Postgres cutover) удалил `init_db` из `web_cabinet.db`. Тесты написаны под SQLite-API.  
**Лечение:** Переписать тесты — использовать Postgres DSN + Alembic или `core.infra.web_db` async-интерфейс.

- `tests/test_t10_03_alerts_aliases.py`
- `tests/test_t10_04_personalization_crud.py`
- `tests/test_t14_02_copilot_tools_step1.py`
- `tests/test_t14_02_copilot_tools_step2.py`
- `tests/test_t14_02_copilot_tools_step3.py`
- `tests/test_t14_02_copilot_tools_step4.py`
- `tests/test_t14_03_weekly_plan_step3.py`
- `tests/test_t14_05_feedback_step3.py`
- `tests/test_t15_09_workflow_core_step1.py`
- `tests/test_t15_09_workflow_core_step3.py`
- `tests/test_t15_09_workflow_core_step4.py`
- `tests/test_t15_09_workflow_core_step5.py`
- `tests/test_t20_01_operational_animal_events.py`
- `tests/test_t21_01_worklist_domain_model.py`
- `tests/test_t21_03_operational_planner.py`
- `tests/test_t21_04_completion_outcome_loop.py`
- `tests/test_t22_02_repro_worklists.py`
- `tests/web/test_t10_03_entity_aliases.py`

---

## Категория C — `ImportError: cannot import name 'init_db' from 'core.infra.web_db'` (21 файл)

**Причина:** Те же тесты, но уже используют канонический модуль `core.infra.web_db` — однако `init_db` туда так и не был добавлен после миграции на Postgres (функция создавала SQLite-схему).  
**Лечение:** Тесты нужно переписать под `asyncpg` / Alembic fixtures; сам `init_db` в Postgres-контуре не нужен.

- `tests/test_t15_10_core_security_audit.py`
- `tests/test_t17_01_observability_core.py`
- `tests/test_t20_02_animal_event_quick_entry.py`
- `tests/test_t20_03_batch_entry.py`
- `tests/test_t21_02_daily_worklists_by_role.py`
- `tests/test_t23_03_vet_triage_queues.py`
- `tests/test_t23_05_health_episode_timeline.py`
- `tests/test_t24_03_fast_query_mode.py`
- `tests/test_t25_02_mobile_worklists.py`
- `tests/test_t25_03_cowside_event_entry.py`
- `tests/test_t25_05_mobile_sync_conflict_audit.py`
- `tests/test_t26_02_migration_verification_toolkit.py`
- `tests/test_t26_05_migration_playbook_and_cutover.py`
- `tests/test_t27_01_cow_value_culling_engine.py`
- `tests/test_t27_02_milk_quality_scc_cockpit.py`
- `tests/test_t27_03_economics_per_action.py`
- `tests/test_t27_04_fresh_cows_transition_economics.py`
- `tests/test_t27_05_operational_what_if.py`
- `tests/test_t28_02_team_shift_management.py`
- `tests/test_t31_02_pilot_adoption_and_roi_metrics.py`
- `tests/test_t31_04_customer_upgrade_and_release_discipline.py`

---

## Категория D — `ImportError: cannot import name 'connect' from 'web_cabinet.db'` (7 файлов)

**Причина:** T34-09 удалил `connect` (низкоуровневый SQLite `sqlite3.connect` wrapper) из `web_cabinet.db`. Тесты дополнительно используют `connect` для прямого доступа к БД.  
**Лечение:** Переписать под Postgres-DSN через `asyncpg.connect` / `GENOMEAI_DB_DSN`.

- `tests/test_t13_06_backup_restore_step1.py` — `from web_cabinet.db import connect, init_db`
- `tests/test_t13_06_backup_restore_step2.py` — `from web_cabinet.db import connect, init_db`
- `tests/test_t15_03_audit_log_migration.py` — `from web_cabinet.db import connect, init_db`
- `tests/test_t15_04_infra_repositories.py` — `from web_cabinet.db import connect, create_job, get_settings, init_db`
- `tests/test_t17_03_migrations_registry.py` — `from web_cabinet.db import connect, init_db`
- `tests/test_t17_04_artifact_lifecycle.py` — `from web_cabinet.db import connect, init_db`
- `tests/test_t17_07_backup_restore_drill.py` — `from web_cabinet.db import connect, init_db`

---

## Категория E — `ImportError: cannot import name 'connect' from 'core.infra.web_db'` (1 файл)

**Причина:** Тест импортирует целый набор удалённых SQLite-функций через канонический модуль.  
**Лечение:** Переписать под новый Postgres-API.

- `tests/test_t28_04_external_collaboration_boundaries.py` — `from core.infra.web_db import connect, create_user_v2, get_user_v2_any_by_username, get_user_v2_any_by_id, get_settings, init_db`

---

## Категория F — Каскадная ошибка через `core.interoperability` (3 файла)

**Причина:** `src/core/interoperability/__init__.py:8` → `migration_verification.py:15` содержит `from core.infra.web_db import init_db`. Любой импорт из `core.interoperability` ломается.  
**Лечение:** Убрать `init_db` из `migration_verification.py` — заменить на Postgres-совместимый способ проверки схемы.

- `tests/test_t26_01_legacy_import_adapters.py`
- `tests/test_t26_03_parallel_run_mode.py`
- `tests/test_t26_04_farm_connector_catalog.py`

Цепочка: `core.interoperability.__init__` → `migration_verification.init_db` → `ImportError`

---

## Категория G — `ImportError: cannot import name 'collect_streamlit_contract'` (1 файл)

**Причина:** Функция `collect_streamlit_contract` не добавлена в `core.public_interfaces` (`src/core/public_interfaces.py`). По-видимому, была запланирована как часть публичного контракта Streamlit-слоя, который уже не используется.  
**Лечение:** Либо добавить stub-функцию в `core.public_interfaces`, либо удалить тест.

- `tests/test_t15_11_public_interfaces_contracts.py`

---

## Дополнительно: warnings при коллекции (не блокируют, но нужно отследить)

| Файл | Тип | Описание |
|---|---|---|
| `src/genomeai/score.py:9` | DeprecationWarning | `genomeai.score` deprecated → `core.application.ml_pipeline` |
| `src/genomeai/train.py:9` | DeprecationWarning | `genomeai.train` deprecated → `core.application.ml_pipeline` |
| `web_cabinet/db.py:5` | DeprecationWarning | `web_cabinet.db` deprecated → `core.infra.web_db` |
| `web_cabinet/rbac.py:11` | DeprecationWarning | `web_cabinet.rbac` deprecated → `core.security` |
| `packages/contracts/api_boundary_v1.py` | UserWarning (×15) | Field name `"schema"` shadows `BaseModel.schema` — Pydantic v2 конфликт |
| `packages/contracts/auth_boundary_v1.py` | UserWarning (×6) | То же |
| `packages/contracts/analytics_v1.py` | UserWarning (×3) | То же |

Pydantic warnings требуют переименования поля `schema` → `schema_` (или `model_config`) во всех契约-файлах.

---

## Приоритет исправления для Недели 2–5

| Приоритет | Категория | Действие |
|-----------|-----------|----------|
| P1 (блокирует всё) | F | Починить `core/interoperability/migration_verification.py:15` — убрать `init_db` |
| P1 (блокирует всё) | G | Добавить `collect_streamlit_contract` stub или удалить тест |
| P2 (39 тестов) | B + D | Переписать импорты `web_cabinet.db.init_db/connect` → Postgres-fixtures |
| P2 (22 теста) | C + E | Переписать импорты `core.infra.web_db.init_db/connect` → Postgres-fixtures |
| P3 (63 теста) | A | Стратегическое решение по `streamlit_app` тестам (удалить / мигрировать / stub) |

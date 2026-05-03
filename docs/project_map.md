# Project map / core migration map

## Canonical layers

- `src/core/domain/` — сущности, dataclass/record модели, enum-контракты
- `src/core/application/` — use-cases и orchestration
- `src/core/infra/` — adapters/repositories/compatibility helpers
- `src/core/security/` — RBAC/policy/permission matrix
- `src/core/audit/` — audit events/search/retention
- `src/core/config/` — единый config loader/validator
- `src/core/reporting/` — fact-pack/reporting use-cases
- `src/core/workflow/` — alerts/tasks/decisions/catalogs/view-models

## Public compatibility surface

- `src/genomeai/cli.py` — основной CLI entrypoint
- `src/genomeai/application/*` — shim-слой к `core.application` / `core.infra`
- `src/genomeai/refactor_verify.py` — low-level legacy facade для Golden compare
- `web_cabinet/*.py` — FastAPI/HTML adapters; бизнес-логика вынесена в core/use-cases

## Target product structure after T32-01

- `apps/api/` — будущий production API слой; сюда должен идти новый server-side boundary code
- `apps/web/` — будущий React/Next.js кабинет
- `web_app/` — новый React/Next.js foundation shell для целевого web UI
- `apps/android/` — будущее отдельное Android-приложение
- `packages/contracts/` — shared contracts между backend/web/mobile
- `packages/domain/` — portable domain vocabulary/value objects при необходимости

## Transitional status

- `web_cabinet/` — legacy server adapter/fallback, который должен поэтапно уступить место explicit API surface в `apps/api/`

Дополнительные repo-level документы для T32-01:

- `docs/target_architecture_web_android_backend.md` — frozen target architecture
- `docs/repo_ownership_map.md` — ownership/status map for repo paths

## Что считается публичным интерфейсом

Контрактно зафиксированы:

- CLI команды
- FastAPI routes
- Ключевые Python entrypoints

Источник истины: `docs/public_interfaces.json`.
Человекочитаемая сводка: `docs/public_interfaces.md`.

## CI gates после T15-12

- `ci/pytest_gate.txt` — минимальный обязательный pytest-набор
- `scripts/run_ci_gate.sh` — локальный/CI запуск pytest-гейта
- `.github/workflows/verify_refactor.yml` — единый PR gate: pytest + web smoke + cleanup/cutover evidence + Golden verification
- `docs/ci_gates.md` — как воспроизводить gates локально
- `docs/operational_sla_and_gates.md` — enterprise operational SLA / rollout gates и diagnostics
- `docs/competitive_acceptance_set.md` — formal competitive acceptance set для legacy replacement readiness
- `docs/demo_farm_and_benchmark_demos.md` — synthetic demo farm dataset, benchmark demos и runnable smoke/setup scripts
- `docs/deprecation_policy.md` — policy для shim deprecations и warning allowlist/budget
- `docs/dependency_warning_audit.md` — audit внешних warnings, tested dependency versions и policy для controlled upgrades
- `docs/warning_governance.md` — CI/runtime policy для allowlist/denylist/budget по warnings

## Cleanup policy

- Новый код добавляется только в `src/core/`
- Старые пути остаются только как shims / thin wrappers
- Временные regression-логи и chunk-списки не хранятся в корне репозитория; они исключены через `.gitignore` и публикуются только как CI artifacts

- `docs/verify_refactor_warning_policy.md` — policy для runtime-warning gate в golden verify path.

- `configs/compat/dependency_warning_inventory_v1.json` — machine-readable inventory tested dependency versions и known external warning issues.

- `configs/compat/test_environment_policy_v1.json` — policy по ключевым пакетам test/runtime environment и правилу controlled upgrades
- `docs/test_environment_reproducibility.md` — как читать `python_environment.json` и зачем он нужен в CI

- `configs/compat/warning_governance_v1.json` — machine-readable allowlist/denylist/budget policy для pytest/smoke warning gates.
- `configs/compat/dependency_update_policy_v1.json` — controlled dependency update policy и правила валидации через warning/pytest/smoke/verify gates.

- `configs/product/commercial_packaging_v1.yaml` — edition/module/feature model и runtime commercial profiles.

- `commercial packaging` — edition/module/feature model и runtime gates для лицензирования и внедрения.
- `docs/replacement_narratives_and_win_themes.md` — replacement narratives, compare checklists, feature maps and proof points tied to actual product capabilities.


## Pilot framework
- `src/core/pilot_framework.py` — core summary builder for pilot tracking and reference deployment evidence rules.
- `data/pilots/pilot_framework_v1/` — starter/sample pilot records for runnable validation.

- `src/core/pilot_adoption_metrics.py` — adoption/usage/ROI metrics builder for pilots.
- `scripts/smoke_t31_02_pilot_adoption_metrics.py` — deterministic smoke for pilot adoption/ROI reporting.

- `src/core/support_sla_incident.py` — support / SLA / incident summary builder, runtime record loader and export helpers.
- `scripts/smoke_t31_03_support_sla_incident_model.py` — deterministic smoke for support operating reports.
- `docs/support_sla_incident_model.md` — support / SLA operating model and runtime record notes.
- Customer upgrade and release discipline (`pages/77_Customer_Upgrade_And_Release_Discipline.py`) — governed upgrade path with support bundle, backup preview, restore drill, release package smoke and rollback criteria.
- Adult deployment baseline (`deploy/adult/*`, `docs/server_deployment_baseline.md`) — reverse proxy, separate web frontend/API/worker/scheduler, PostgreSQL, Redis, MinIO, Prometheus, env profiles and backup/restore host scripts.
- Production security / IAM baseline (`docs/production_security_and_iam_baseline.md`, `configs/security/*`, `deploy/adult/security/*`, `deploy/adult/secrets/*`) — token policy, file-based secrets, TLS/security headers, network boundaries, service trust baseline and on-prem security checklist.

- commercial readiness gate

- `web_app/` — target React/Next.js cabinet; T32-05 adds daily operations parity surfaces (`/daily-summary`, `/alerts`, `/worklists`, `/planner`) over canonical backend contracts.
- `mobile_android/` — target Kotlin/Jetpack Compose field app foundation; T32-08 adds auth-aware shell, role-aware navigation, sync-safe baseline and first cowside screens.
- `configs/cutover/` — formal web cutover gate, coexistence/rollback runbook and approval artifacts.
- `configs/post_removal/` — post-removal regression, legacy cleanup manifest/report and no-tail verification artifacts.

- docs/react_profiles_reports_assistant_parity.md — parity note for profiles / reports / assistant / explainability in React.
- docs/react_extended_surface_parity.md — parity note for reproduction / vet / treatments / economics / admin / observability / support / pilot / readiness in React.

- `docs/android_field_app_foundation.md` — Android field app foundation, separate-app rule and first cowside scope.

- T32-11A web cutover / coexistence / rollback runbook: docs/web_cutover_and_rollback_runbook.md

- `docs/deployment_full_guide.md` — полная пошаговая инструкция по развёртыванию backend + web + workers/scheduler + PostgreSQL/Redis/MinIO + TLS + Android build baseline.
- `docs/ui_functional_verification_web.md` — пошаговая функциональная проверка нового web UI по ролям и сценариям.
- `docs/ui_functional_verification_android.md` — пошаговая функциональная проверка Android field app, включая cowside и offline/sync baseline.
- `docs/full_uat_checklist.md` — сводный pass/fail checklist для QA / implementation / customer UAT.
- `docs/operations_runbook.md` — operations runbook для install/upgrade/rollback/incident/support.

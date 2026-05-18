# T34 P1-tails Execution Proof — P1-4 R7/R19, P1-6b slice 1, P1-5 slice 4

**Date:** 2026-05-18
**Source brief:** docs/iterations/T34-product-backlog-2026-05.md (P1 active items)
**Driver:** Coordinator directive — «делаем P0, потом закрываем P1»

## Scope

Закрытие реального остатка P1 после backlog-audit'а, который выявил, что P0-4, P1-1, P1-2, P1-3 уже закрыты ранее (backlog был устаревшим). Три фактических доработки:

1. **P1-4 R7+R19** — UserPicker вместо `<input type=number>` для `user_id` в personnel-edit-modal.
2. **P1-6b slice 1** — admin enable/disable toggle для интеграций (migration + storage + permission + endpoint + UI).
3. **P1-5 slice 4** — IAM matrix interactive editing с 2-click confirm и предупреждением о session-cache R4.

## Net result

| Эпик | Состояние до | Состояние после |
|------|--------------|------------------|
| P1-4 R7/R19 | personnel-edit-modal принимает raw user_id number | UserPicker с поиском по active auth-users из `/api/users_v2`; fallback на input при недоступности endpoint |
| P1-6b slice 1 | `/admin/integrations` read-only | Toggle button per-row gated `integrations.manage`; PATCH /api/app/v1/integrations/{id}; admin-disabled rows показывают status=disabled с note «Отключено администратором» |
| P1-5 slice 4 | Матрица read-only (checkboxes disabled) | Чекбоксы интерактивные для admin.manage; Modal confirm с R4-warning; PATCH /api/admin/permission-matrix; toast с effective count |

## Acceptance criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Все 7 CI гейтов зелёные | ✅ | См. таблицу гейтов ниже |
| 2 | TypeScript build чистый (web_app) | ✅ | `npx tsc --noEmit` exit 0; `npm run build` все 32 страницы без errors/warnings |
| 3 | Existing P1-6 tests не сломаны | ✅ | `pytest tests/test_t34_p1_6_integrations_health.py` — 7/7 passed |
| 4 | apply_overrides logic корректен | ✅ | Unit-инвокация: admin-disabled row → status=disabled с note; admin-enabled override → unchanged (provider wins); no-override → unchanged |
| 5 | Backend routes зарегистрированы | ✅ | `PATCH /api/app/v1/integrations/{integration_id}` присутствует в `router.routes`; permission gate `integrations.manage` |
| 6 | `PERM_INTEGRATIONS_MANAGE` в ALL_PERMISSIONS | ✅ | `core.security.policy` — добавлен в ALL_PERMISSIONS → автоматически доступен роли Admin |
| 7 | Контракт расширен и зарегистрирован | ✅ | `IntegrationPatchRequest` в `packages/contracts/integrations_health_v1.py`; PATCH endpoint в `docs/public_interfaces.json` |
| 8 | R4 (cache invalidation) mitigated в UI | ✅ | Modal confirm в IamMatrix содержит warning «Изменение применится только при следующем входе пользователей этой роли» |

## Executed checks (7 CI gates per CLAUDE.md §4)

| # | Gate | Result | Artifact |
|---|------|--------|----------|
| 1 | `bash scripts/run_ci_gate.sh` | ✅ PASSED — Python syntax / TS typecheck / no secrets / web_cabinet imports | (output captured in shell) |
| 2 | `python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean --timing-json ...` | ✅ `WEB_SMOKE_OK` | `artifacts/_ci/web_smoke.log`, `artifacts/_ci/web_smoke.json` |
| 3 | `python -m genomeai.cli verify_refactor --project-root . --golden golden --report-root ...` | ✅ `VERIFY_REFACTOR_OK` — 2/2 scenarios ok, 0 differences | `artifacts/_ci/verify_refactor/verify_20260518_184312/verify_report.{json,md}` |
| 4 | `bash scripts/run_warning_governance_gate.sh` | ✅ `WARNING_GOVERNANCE_OK` | `artifacts/_ci/warning_governance_report.json` |
| 5 | `bash scripts/run_operational_rollout_gate.sh` | ✅ `OPERATIONAL_ROLLOUT_GATES_OK` — 5/5 gates within budget | `artifacts/_ci/operational_rollout_gates/operational_rollout_gates_report.{json,md}` |
| 6 | `bash scripts/run_competitive_acceptance_gate.sh` | ✅ `COMPETITIVE_ACCEPTANCE_READY_FOR_UAT=true` — 6/6 сценариев ready | `artifacts/_ci/competitive_acceptance/competitive_acceptance_report.{json,md}` |
| 7 | `bash scripts/run_perf_gates.sh` | ✅ `PERF_GATES_OK` — startup/pipeline_smoke/web_smoke/verify_refactor все в бюджете | `artifacts/_ci/performance_gates/performance_gates_report.{json,md}` |

## Honest status

**`proven`** — все 7 гейтов CLAUDE.md §4 зелёные, изменённые компоненты компилируются и существующие тесты проходят. Миграция `20260518_20_integration_overrides` готова и применится при следующем `alembic upgrade head`; web_smoke в gate 2 успешно использовал postgres backend.

Не проверено (out-of-scope для прогона гейтов):
- Live Playwright runtime smoke на /team, /admin/integrations, /admin/iam — отложен; требует поднятого uvicorn + npm run dev одновременно.
- End-to-end сценарий «admin отключает интеграцию → видит status=disabled с note» через настоящий UI — gates это покрывают только косвенно (через unit + import smoke).

## Files touched

### New
- `src/core/migrations/alembic/versions/20260518_20_integration_overrides.py`
- `src/core/workflow/integration_overrides.py`
- `web_app/components/team/user-picker.tsx`
- `web_app/lib/api/users-v2.ts`

### Modified
- `src/core/security/policy.py` — `PERM_INTEGRATIONS_MANAGE`
- `packages/contracts/integrations_health_v1.py` — `IntegrationPatchRequest`
- `web_cabinet/api_boundary_v1.py` — PATCH endpoint + apply_overrides on GET
- `web_app/lib/api/integrations.ts` — `patchIntegrationEnabled`
- `web_app/components/admin/integrations-surface.tsx` — toggle button
- `web_app/lib/api/iam.ts` — `patchPermissionOverride`
- `web_app/components/admin/iam-matrix.tsx` — interactive checkboxes + confirm Modal
- `web_app/components/team/personnel-edit-modal.tsx` — UserPicker integration
- `docs/public_interfaces.json` — PATCH /integrations/{id} registered
- `docs/iterations/T34-P1-4_risks_and_assumptions.md` — R7/R19 closed
- `docs/iterations/T34-P1-5_risks_and_assumptions.md` — slice 4 closed
- `docs/iterations/T34-P1-6_risks_and_assumptions.md` — slice 1 closed
- `docs/iterations/T34-product-backlog-2026-05.md` — P0-4/P1-1/P1-2/P1-3 marked closed (audit), P1-4 R-debt + P1-5 slice 4 + P1-6b slice 1 closure documented

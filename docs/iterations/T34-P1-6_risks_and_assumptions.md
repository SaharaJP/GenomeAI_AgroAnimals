# T34 P1-6 «Контроль интеграций» — реестр рисков и допущений

> Снапшот на 2026-05-15. Read-only фаза закрыта; action layer (manual sync,
> enable/disable, deep-link в логи) вынесен в отдельный P1-6b и пока не делается.

---

## Архитектура

- **A1.** Один источник истины формы данных — `packages/contracts/integrations_health_v1.py` (Pydantic). Frontend mirror — `web_app/lib/api/integrations.ts`. Bounded `kind` ∈ {llm, batch_connector, iot_device, external_system, sensor_ingestion}, bounded `status` ∈ {ok, degraded, down, disabled}.
- **A2.** Pluggable provider-протокол `IntegrationHealthProvider.get_health(conn) -> list[IntegrationHealth]` в `src/core/interoperability/integrations_health.py`. Регистрация — через side-effect на import пакета `core.interoperability.providers`. Endpoint lazy-импортирует пакет, провайдеры регистрируются автоматически.
- **A3.** Один row per source-system. Селекс/1С имеют **по одной row**, даже хотя batch-pipeline (текущий) и live API (P2-4) — две разные имплементации. Status показывает текущий batch, note подсвечивает upcoming P2-4 upgrade. Это сознательное решение для пользовательской ясности — одна сущность = одна строка.
- **A4.** Provider-failures изолированы: если `provider.get_health()` бросает исключение, `collect_health` ловит, логирует и возвращает синтетическую row с `id='_error.<ProviderName>'`, `status='down'`, `last_error=<exc>`. Endpoint не падает, остальные провайдеры продолжают работать.

## Поведение providers

- **A5.** **LLM provider.** Сейчас проверяет только presence `OPENAI_API_KEY` или `OPENAI_API_KEY_FILE` (с реальным чтением файла). НЕ делает ping в OpenAI — это $$ и rate-limit. Status `ok` ≠ "OpenAI отвечает", а "credentials configured".
- **A6.** **Connectors_v1 provider.** Энумерует `configs/connectors/*.yaml` (active) + `configs/connector_catalog/*.yaml` (blueprints), группирует по `source_system`, для active configs делает join с `connector_runs` table. Подключает note про P2-4 upgrade для Селекс / 1С.
- **A7.** **IoT stubs.** Шесть фиксированных classes (collar/bolus/ear_tag/leg_band/smart_scale/camera). Всегда `disabled` + note "P2-3". ID стабильны (`iot.<class>`) — когда P2-3 имплементирует реальные провайдеры, они могут заменить stubs с тем же id без миграции UI.
- **A8.** **Хэрриот stub.** Single row `external.herriot` в `ru_stubs.py`. Note про сертификаты УЦ Россельхознадзора и P2-4 дорожку C.

## Риски

- **R1.** **`status=ok` для LLM не отражает реальную доступность OpenAI.** Если ключ валиден, но OpenAI down — UI продолжит показывать ok. Mitigation для P1-6b: lazy ping раз в 5 минут с кешем; либо берём last successful request из `ai_calls` audit-tail если он есть.
- **R2.** **Connectors_v1 health requires 1 SQL query per source-system.** Сейчас ~7 систем = 7 queries на каждый GET. С учётом auto-refresh раз в 30s = 14 queries/min на пользователя. Допустимо для admin-страницы (≤ 5 одновременных пользователей). В P2 — единый aggregate query (`SELECT DISTINCT ON (connector_id) ... ORDER BY started_at DESC`) или materialized view.
- **R3. ✅ RESOLVED (P1-5/P1-6 R-debt 2026-05-15).** `IntegrationHealthProvider.get_health(conn, *, tenant_id)` теперь принимает `tenant_id`, endpoint пробрасывает `user.tenant_id` из сессии. `ConnectorsV1HealthProvider` использует его вместо хардкода. Tenant-agnostic providers (LLM, IoT, RU stubs) аргумент игнорируют.
- **R4.** **Auto-refresh = 30s.** На странице открытой 8 часов = 960 запросов. Каждый запрос делает RBAC-check + 5 providers. Не критично, но в P2 можно добавить ETag + If-None-Match для дельты.
- **R5.** **Сводный статус ("Отключено" в topbar) не учитывает stubs.** Если все real-провайдеры disabled (нет OPENAI_API_KEY, нет batch run'ов), aggregate = `disabled`, что выглядит как "вся платформа disabled". Текстовый label это уточнить не помогает. В P1-6b добавить tooltip "Real-провайдеры: X из Y активны".
- **R6. ✅ RESOLVED (P1-5/P1-6 R-debt 2026-05-15).** `PERM_INTEGRATIONS_VIEW` добавлена в `DEFAULT_ROLE_PERMISSIONS[Director]`. Director теперь видит `/admin/integrations` по умолчанию. Operator/Vet/etc остаются без права — могут получить через P1-5 PATCH /admin/permission-matrix grant override.

## Допущения

- **A9.** Секреты на странице не показываются ни в каком виде. `last_error` подрезается до 200 символов в isolation-row. В P1-6b при добавлении manual sync — экранировать stack trace перед записью в payload.
- **A10.** Auto-refresh идёт через `setInterval`, не через SWR/React Query (не подключены в проекте). Если пользователь открывает страницу в фоновом табе, refresh продолжается — допустимо для P1, в P2 — `document.visibilityState`.
- **A11.** `latency_ms` и `records_in_last_window` сейчас `null` для всех rows (LLM не пингует, batch не считает в провайдере). Поля забронированы в контракте под P1-6b/P2.
- **A12.** P1-6 не вводит persistent storage для health snapshots. Каждый GET = fresh query. Если когда-то потребуется history (графики availability), нужна отдельная таблица + collector worker.

## Что НЕ сделано (P1-6b) — обновлено 2026-05-18

### Slice 1 (2026-05-18, текущая итерация) — ✅ ЗАКРЫТО
- ✅ Enable / disable toggle для каждой интеграции — DB-override layer (`integration_overrides_v1`, миграция `20260518_20`), аналогично P1-5 role overrides.
- ✅ Audit `integration.toggle.enable` / `integration.toggle.disable`.
- ✅ New permission `integrations.manage` (`PERM_INTEGRATIONS_MANAGE` в policy.py, в `ALL_PERMISSIONS` → доступно Admin).
- ✅ PATCH `/api/app/v1/integrations/{integration_id}` с `{enabled: bool}` body.
- ✅ `apply_overrides` в `core.workflow.integration_overrides`: rows админом disabled показываются status='disabled' с note «Отключено администратором».
- ✅ Frontend toggle button per-row на `/admin/integrations`, gated `integrations.manage`.

### Slice 2 (2026-05-18) — ✅ ЗАКРЫТО (LLM-only MVP)
- ✅ Manual sync кнопка на каждой строке `/admin/integrations` (UI gated `integrations.manage`).
- ✅ Backend endpoint `POST /api/app/v1/integrations/{id}/sync` с dispatcher `core.workflow.integration_sync.trigger_sync`.
- ✅ Реальный ping LLM провайдера через `openai.models.list()` — закрывает R1 для OpenAI режима (latency_ms измеряется реально).
- ✅ Audit-event `integration.manual_sync` с outcome (ok/message/duration_ms) в after_json.
- ✅ Toast в UI показывает результат: ✓/✗ + message + длительность.
- ✅ **Slice 2b (2026-05-18):** `batch.*` connectors поддержаны через `genomeai.connectors_v1.run_connector_spec` (синхронный для текущих stub-конфигов — `api_stub_demo`, `file_demo`, `onec_stub_demo`). Когда появятся real-coннекторы Селекс/1С — переключить на `core.application.job_runner.enqueue_pipeline_job` для async-режима.
- ⏸ **Tooltip про real vs stubs (R5) и Live LLM cache (R1)** — отдельная косметическая итерация.

### Slice 3 (отложен)
- Deep-link "Открыть логи" из row → `/admin/logs?source=<connector_id>` (раздел `/admin/logs` сам ещё не существует, нужен отдельный logs viewer).

## Сводка приоритетов для будущего P1-6b

| ID | Уровень | Что | Зачем |
|---|---|---|---|
| R1 | средний | LLM ok не = OpenAI доступен | misleading status |
| ~~R3~~ | ✅ resolved | ~~tenant_id хардкод в batch provider~~ | passthrough в P1-5/P1-6 R-debt 2026-05-15 |
| ~~R6~~ | ✅ resolved | ~~integrations.view только у admin~~ | Director в DEFAULT_ROLE_PERMISSIONS в P1-5/P1-6 R-debt 2026-05-15 |
| R2 | низкий | N queries per GET | scale |
| R4 | низкий | 30s polling без ETag | network noise |
| R5 | низкий | aggregate status не считает stubs | UX clarity |

## Public interface footprint

- `GET /api/app/v1/integrations/health` — read-only; gate `integrations.view`. Зарегистрирован в `docs/public_interfaces.json`.
- `PATCH /api/app/v1/integrations/{integration_id}` (P1-6b slice 1, 2026-05-18) — body `{enabled: bool}`; gate `integrations.manage`. Audit-event `integration.toggle.{enable|disable}` с `before`/`after`. Зарегистрирован в `docs/public_interfaces.json`.
- `POST /api/app/v1/integrations/{integration_id}/sync` (P1-6b slice 2, 2026-05-18) — manual sync trigger; gate `integrations.manage`. Возвращает `{integration_id, ok, duration_ms, message, detail}`. Audit-event `integration.manual_sync`. Currently LLM ping only; batch/IoT возвращают 400 `sync.not_supported`. Зарегистрирован в `docs/public_interfaces.json`.
- Deep-link logs endpoint — будет добавлен в slice 3.

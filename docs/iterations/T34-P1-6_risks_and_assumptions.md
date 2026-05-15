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
- **R3.** **`tenant_id='default'` хардкоден в connectors_v1 provider.** На multi-tenant контурах admin одного тенанта увидит только свои батч-прогоны. Это корректное поведение, но требует passthrough `user.tenant_id` через `get_health(conn, *, tenant_id)`. Сейчас всем provider'ам передаётся только `conn` — расширить интерфейс в P1-6b.
- **R4.** **Auto-refresh = 30s.** На странице открытой 8 часов = 960 запросов. Каждый запрос делает RBAC-check + 5 providers. Не критично, но в P2 можно добавить ETag + If-None-Match для дельты.
- **R5.** **Сводный статус ("Отключено" в topbar) не учитывает stubs.** Если все real-провайдеры disabled (нет OPENAI_API_KEY, нет batch run'ов), aggregate = `disabled`, что выглядит как "вся платформа disabled". Текстовый label это уточнить не помогает. В P1-6b добавить tooltip "Real-провайдеры: X из Y активны".
- **R6.** **Permission `integrations.view`** добавлена только в `ALL_PERMISSIONS`. Admin наследует через ALL_PERMISSIONS. Другим ролям (Director/Operator) право явно не назначено — они получат 403 на GET /integrations/health. Чтобы расширить — admin должен через P1-5 PATCH /api/admin/permission-matrix сделать grant.

## Допущения

- **A9.** Секреты на странице не показываются ни в каком виде. `last_error` подрезается до 200 символов в isolation-row. В P1-6b при добавлении manual sync — экранировать stack trace перед записью в payload.
- **A10.** Auto-refresh идёт через `setInterval`, не через SWR/React Query (не подключены в проекте). Если пользователь открывает страницу в фоновом табе, refresh продолжается — допустимо для P1, в P2 — `document.visibilityState`.
- **A11.** `latency_ms` и `records_in_last_window` сейчас `null` для всех rows (LLM не пингует, batch не считает в провайдере). Поля забронированы в контракте под P1-6b/P2.
- **A12.** P1-6 не вводит persistent storage для health snapshots. Каждый GET = fresh query. Если когда-то потребуется history (графики availability), нужна отдельная таблица + collector worker.

## Что НЕ сделано (P1-6b)

- Manual sync кнопка на real-rows (LLM ping, connector_runs trigger).
- Enable / disable toggle для каждого connector (write в `configs/connectors/*.yaml.enabled` или DB-override layer аналогично P1-5).
- Deep-link "Открыть логи" из row → `/admin/logs?source=<connector_id>` (этот раздел сам ещё не существует).
- Audit `integration.manual_sync` / `integration.enabled` / `integration.disabled`.
- New permission `integrations.manage`.
- Tooltip на сводном статусе про real vs stubs (R5).
- Per-tenant scoping в connectors_v1 provider (R3).
- Live ping LLM с кешем (R1).

## Сводка приоритетов для будущего P1-6b

| ID | Уровень | Что | Зачем |
|---|---|---|---|
| R1 | средний | LLM ok не = OpenAI доступен | misleading status |
| R3 | средний | tenant_id хардкод в batch provider | multi-tenant correctness |
| R6 | средний | integrations.view только у admin | Director/operator UX |
| R2 | низкий | N queries per GET | scale |
| R4 | низкий | 30s polling без ETag | network noise |
| R5 | низкий | aggregate status не считает stubs | UX clarity |

## Public interface footprint

- `GET /api/app/v1/integrations/health` — read-only; gate `integrations.view`. Зарегистрирован в `docs/public_interfaces.json`.
- Никаких других endpoint'ов P1-6 не добавляет. PATCH/POST appear in P1-6b.

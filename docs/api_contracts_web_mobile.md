# T32-02 — API contracts for web/mobile boundary

Статус: active target boundary  
Дата: 2026-04-12

## Цель

Зафиксировать **backend API как единственную точку входа** для будущих `apps/web` и `apps/android`, не ломая текущие CLI / jobs / artifacts / version lineage.

## Ключевое правило

Новый web/mobile UI **не должен**:

- импортировать `core.*`, `genomeai.*`, `web_cabinet.*` напрямую;
- читать SQLite / artifacts напрямую;
- строить implicit DTO из внутренних Python-словарей.

Новый web/mobile UI должен работать через:

- backend endpoints в namespace `GET|POST /api/app/v1/*`
- versioned contracts из `packages/contracts/api_boundary_v1.py`

## Что считается boundary, а что нет

### Boundary / target

- `packages/contracts/api_boundary_v1.py` — shared DTO/contracts
- `web_cabinet/api_boundary_v1.py` — façade/router над внутренними use-cases и repo APIs
- `/api/app/v1/*` — target namespace для React/Next.js и Android

### Transitional / legacy

- существующие `/api/alerts_v2`, `/api/tasks_v1`, `/api/decision_log_v2`, `/api/weekly_plans_v1`, `/api/whatif_*`, `/api/feedback_v1`
- HTML routes `web_cabinet/templates/*`
- no direct UI access to internal Python modules; standalone web and Android use backend API only

Legacy endpoints не удаляются на этом шаге, но **новый UI обязан опираться на boundary namespace**, а не на legacy route map.

## DTO vs domain

### Domain / internal model

Внутренние модели остаются в:

- `src/core/domain/*`
- `src/core/workflow/*`
- `src/core/infra/*`
- `genomeai/*`

Они могут хранить:

- внутренние поля хранения;
- append-only/audit семантику;
- внутренние reason codes;
- backend-specific payload layout.

### UI DTO / contracts

DTO для web/mobile вынесены в `packages/contracts/api_boundary_v1.py`.

Они:

- стабильнее внутренних словарей;
- отделены от sqlite/repo layouts;
- пригодны и для React, и для Android;
- сохраняют linkage к `data_version/qc_run/model_version/scoring_run/report_version`.

## Реализованный namespace

### Alerts

- `GET /api/app/v1/alerts`

Contract: `AlertsListResponse`

### Worklists

- `GET /api/app/v1/worklists`

Contract: `WorklistsListResponse`

### Planner

- `GET /api/app/v1/planner`

Contract: `PlannerResponse`

Содержит:

- workflow summary;
- weekly plans;
- pending approvals;
- overdue items.

### Profiles

- `GET /api/app/v1/profiles/{object_type}/{object_id}`

Contract: `ProfileResponse`

Profile façade агрегирует:

- alerts;
- worklists;
- decisions.

### Reports

- `GET /api/app/v1/reports`

Contract: `ReportsListResponse`

### Assistant

- `POST /api/app/v1/assistant/resolve-target`

Contract:

- request: `AssistantResolveTargetRequest`
- response: `AssistantResolveTargetResponse`

На этом шаге assistant boundary даёт **governed fact resolution contract**, а не полный chat/session API.

### Decisions

- `GET /api/app/v1/decisions`

Contract: `DecisionsListResponse`

### Feedback

- `GET /api/app/v1/feedback`

Contract: `FeedbackListResponse`

### Economics

- `GET /api/app/v1/economics`

Contract: `EconomicsListResponse`

### Support

- `GET /api/app/v1/support`

Contract: `SupportResponse`

## Почему это backend-first split

1. Web/mobile получают **единый contract namespace**.
2. Внутренние workflow/repo функции не становятся публичным интерфейсом.
3. Boundary слой может эволюционировать независимо от legacy HTML/Streamlit.
4. Domain logic остаётся в backend, без дублирования в React/Android.

## Ограничения текущего шага

- Это **первый façade-layer**, а не полная миграция всех legacy APIs.
- Legacy `/api/*_v1|v2` ещё живы и используются текущим кабинетом.
- Assistant boundary пока ограничен resolved fact target flow.
- Полный typed OpenAPI client generation для React/Android пока не добавлен.

## Правило для следующих итераций

Любой новый web/mobile flow должен идти в таком порядке:

1. новый/обновлённый contract в `packages/contracts/*`
2. новый façade endpoint в `/api/app/v1/*`
3. тесты на contract shape
4. только потом реализация в `apps/web` или `apps/android`

## Связь с T32-01

T32-01 заморозил target architecture и запретил новый product UI в Streamlit.  
T32-02 добавляет **первую реальную boundary-поверхность**, через которую web/mobile смогут идти без прямого доступа к внутренним модулям.

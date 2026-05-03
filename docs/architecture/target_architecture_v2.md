# Target architecture v2

## 1. Цель

Перевести GenomeAI AgroAnimals из режима `offline-core + Streamlit/mini-web adapters` в архитектуру уровня production:

- **Backend API** — единый слой доступа к данным, use-cases, workflow, audit и version lineage.
- **Web frontend** — полноценный кабинет для ролей руководитель / herd manager / vet / breeding / repro / admin.
- **Android app** — отдельный мобильный контур для cowside execution.
- **Shared contracts/domain** — общие контракты данных и терминология.
- **Server runtime** — production-ready deployment topology.

## 2. Архитектурные принципы

### 2.1 Backend как единственный источник правды

Backend отвечает за:

- auth/session/token/tenant context;
- RBAC/permission checks;
- audit log;
- job orchestration;
- decision log;
- workflow state;
- source linkage и version lineage;
- fact-pack / report generation;
- экспорт и артефакты.

UI-контуры не принимают решений за backend.

### 2.2 Shared contracts обязательны

Любой новый пользовательский сценарий должен иметь:

1. контракт запроса;
2. контракт ответа;
3. error contract;
4. audit implications;
5. RBAC expectations;
6. versioning rule.

### 2.3 Web и Android разделены по назначению

**Web**:

- аналитика;
- кабинетные workflow;
- настройка справочников и политик;
- дашборды;
- approvals;
- audit / admin / integrations / release diagnostics.

**Android**:

- быстрый operational input;
- worklists;
- task execution;
- event capture;
- cowside confirmations;
- offline-first local queue + sync.

## 3. Целевой logical decomposition

### 3.1 Core domain/application

Остаётся в `src/core/` и продолжает быть местом для:

- domain models;
- application use-cases;
- workflow policies;
- ML/reporting orchestration;
- QC policies;
- audit/security rules.

### 3.2 API layer

Будущий `apps/api/` должен включать:

- HTTP API;
- auth/token/session boundary;
- request validation;
- API DTO mapping;
- background job triggers;
- webhook/internal callbacks;
- readiness/liveness/admin endpoints;
- OpenAPI publishing.

### 3.3 Web frontend

Будущий `apps/web/` должен включать:

- role-based routing;
- design system;
- state/query layer;
- forms and tables;
- dashboard pages;
- report/review/download surfaces;
- operator/admin/integration screens.

### 3.4 Android app

Будущий `apps/android/` должен включать:

- authentication and device session;
- local persistence for offline queue;
- sync engine with conflict policy;
- task/worklist/event-entry flows;
- minimal animal/group context;
- upload of attachments/photo evidence when needed.

### 3.5 Shared contracts

`packages/contracts/` должно стать местом для:

- OpenAPI snapshots or generated clients;
- shared enums;
- request/response JSON schemas;
- mobile/web compatibility notes;
- contract changelog and version policy.

## 4. Данные и runtime topology

Production-oriented target:

- relational database for transactional state;
- object storage for artifacts/reports/uploads/raw snapshots;
- workers for heavy jobs;
- scheduler for periodic jobs;
- observability stack for logs/metrics/traces;
- backup/restore discipline;
- release discipline with rollback path.

## 5. Streamlit status

`removed_streamlit_legacy/` больше не является target UI.

Его статус:

- transitional;
- compatibility surface;
- parity reference;
- temporary fallback until cutover.

Любые новые продуктовые сценарии должны проектироваться так, как будто Streamlit уже не существует.

## 6. Definition of done для полной миграции

Миграция считается завершённой только когда:

- кабинетный ежедневный контур работает в web frontend;
- cowside daily execution работает в Android;
- Streamlit не нужен для новых продаж и внедрений;
- backend API покрывает все ключевые use cases;
- все критичные legacy сценарии имеют parity evidence;
- deployment/runbooks ориентированы на server-grade runtime, а не на локальный all-in-one режим.

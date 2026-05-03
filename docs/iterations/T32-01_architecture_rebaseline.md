# T32-01 — Architecture rebaseline: backend API + web frontend + Android + shared contracts

## Контекст

До этого этапа репозиторий развивался как `offline-core + mini-web + Streamlit shell`. Это дало рабочий MVP+/MVP++ контур, но больше не совпадает с новой целевой продуктовой архитектурой.

Новая целевая модель:

- backend API = единый источник правды;
- отдельный web frontend для кабинетной работы;
- отдельное Android-приложение для работы в полях;
- shared contracts/domain между контурами;
- Streamlit допускается только как transitional layer до formal cutover.

## Что фиксирует эта итерация

1. Целевую архитектуру и границы ответственности.
2. Статус Streamlit как transitional/deprecated surface.
3. Каркас будущих контуров `apps/api`, `apps/web`, `apps/android`, `packages/contracts`, `packages/domain`.
4. Production-oriented server target: API, auth, workers, scheduler, DB, object storage, observability, backup/restore.
5. Правило: весь новый продуктовый UI-код идёт в web/android, а не в Streamlit.

## Что не делаем в этой итерации

- не переносим существующие страницы Streamlit в React/Next.js;
- не переписываем существующий FastAPI/mini-web целиком;
- не меняем бизнес-логику в `src/core`;
- не вводим сразу новую БД/очередь/объектное хранилище в runtime;
- не удаляем Streamlit и не объявляем cutover.

## Целевая структура репозитория (пока как skeleton)

- `src/core/` — домен, use-cases, policies, reporting, workflow, security.
- `apps/api/` — будущий production API слой.
- `apps/web/` — будущий web кабинет (React/Next.js).
- `apps/android/` — будущее нативное Android-приложение.
- `packages/contracts/` — DTO/JSON schemas/OpenAPI-derived contracts/versioned API payload shapes.
- `packages/domain/` — shared domain vocabulary/value objects/rules, если часть потребуется вынести из Python-core в language-agnostic contracts.

## Migration policy

### API

- Любой новый UI use case сначала формализуется как backend contract.
- Временные server-rendered/legacy маршруты допустимы только как compatibility layer.
- Источник правды по данным, правам, audit и decision log — backend.

### Web

- Новый кабинетный UI разрабатывается только в `apps/web/`.
- Web не содержит бизнес-логики, расчётов confidence, ранжирования, reason codes или RBAC-решений.
- Web вызывает API и рендерит результат.

### Android

- Android — отдельное приложение для cowside/daily execution.
- Android поддерживает офлайн-очередь/синхронизацию только через backend contracts.
- Android не дублирует кабинетные аналитические сценарии, кроме легковесных operational summaries.

### Streamlit

- `streamlit_app/` — transitional UI only.
- Разрешено:
  - bugfix/support;
  - parity verification;
  - временные экраны до cutover, если нет другой опции.
- Запрещено:
  - писать в Streamlit новый целевой продуктовый UI;
  - вводить в Streamlit новую бизнес-логику;
  - объявлять Streamlit primary target architecture.

## Cutover gates (верхнеуровнево)

Удаление Streamlit допустимо только после одновременного выполнения:

1. Web покрывает все кабинетные критичные сценарии.
2. Android покрывает утверждённый cowside scope.
3. Все операции идут через backend API.
4. RBAC/audit/source linkage/version lineage идентичны legacy surface.
5. Есть smoke/e2e/regression parity evidence.
6. Есть rollback plan и formal go/no-go.

## Следующие итерации после T32-01

- T32-02: API boundary inventory и mapping legacy routes/pages -> target endpoints.
- T32-03: shared contracts baseline (versioning, DTO, OpenAPI source of truth).
- T32-04: web frontend shell bootstrap.
- T32-05: Android shell bootstrap.
- T32-06: server runtime target (workers/scheduler/storage/observability) as executable deploy plan.

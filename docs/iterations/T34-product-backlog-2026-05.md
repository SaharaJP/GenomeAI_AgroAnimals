# T34 — Product backlog (UI / навигация / интеграции / AI)

> Создан: 2026-05-12
> Источник: запрос координатора от 2026-05-12 ночью.
> Статус: backlog, ничего из перечисленного **не реализовано** — это план работы.
> Все эпики разбиваются на инкременты строго по правилу CLAUDE.md §3 (один ответ = один маленький шаг).

---

## 0. Контекст и инвентаризация существующего

Перед оценкой проверил текущий код, чтобы каждая задача имела привязку к реальным файлам:

- **Навигация** — централизована: `web_app/lib/navigation.ts` (один источник правды для сайдбара, секции `Основное`/`Управление`/`Сервисы`). Переименования вкладок и переструктуризация — точечные правки одного файла + соответствующих маршрутов в `web_app/app/(protected)/...`.
- **Помощник «Брифинг фермы»** — уже разложен на части: `web_app/components/copilot/{create-brief-card, brief-preview, past-briefings-list, settings-card}.tsx`. Для задачи 5 не надо строить компонент с нуля — нужна обёртка-модалка над существующими.
- **Обзор / Daily summary** — `app/(protected)/daily-summary`, `components/overview/{morning-brief-card, weekly-brief-card}.tsx`.
- **Рабочие списки** — `app/(protected)/worklists`, `components/operations/worklists-surface.tsx`.
- **Профили животных** — `app/(protected)/profiles`, отдельные маршруты `reproduction`, `vet`, `treatments`.
- **Админка** — `app/(protected)/admin/` уже содержит подмаршрут `ai`.
- **Sensor ingestion** — есть **только** документ `docs/integrations/sensor_ingestion_api.md` и `src/genomeai/sensor_anomaly_v1.py`. Конкретного IoT-коннектора, демо-эмулятора и привязки к карточкам животных **нет** — это полноценный эпик.
- **LLM-клиент** — `src/core/reporting/{assistant_reporting,regular_reporting}.py` бьются в **OpenAI** (модель `gpt-4o-mini` через `OPENAI_API_KEY`). Никакого Claude в runtime сейчас нет; миграция «на Ollama» — это миграция с OpenAI-клиента + всех мест, где он используется.
- **Next.js dev-overlay кнопка** — стандартный dev indicator Next.js 15, отключается через `next.config.ts`.

---

## 1. Принципы приоритезации

Каждая задача оценена по 4 осям:

| Ось | Расшифровка |
|-----|-------------|
| **Effort** | S (≤1 день), M (1–3 дня), L (1–2 недели), XL (>2 недель, эпик) |
| **Risk** | low / med / high — с точки зрения CLAUDE.md (auth/RBAC/golden/migrations/secrets) |
| **Value** | пользовательская / демо-видимая ценность |
| **Deps** | блокеры или порядок выполнения |

Приоритеты:
- **P0** — мелкая косметика + переименования, разблокирует UX и не требует backend-миграций. Делать **первым**.
- **P1** — связки данных (инсайты ↔ задачи, задачи ↔ Команда, Стадо ↔ суб-вкладки). Видимая бизнес-ценность.
- **P2** — крупные эпики (IoT, Экономика, Ollama). Требуют отдельных RFC, гейтов и contract-обновлений.

---

## 2. Бэклог (сначала P0, потом P1, потом P2)

### P0-1. Скрыть Next.js dev-indicator
- **Источник запроса:** «убрать в нижнем левом углу кнопку от next.js».
- **Effort:** S.
- **Risk:** low.
- **Что делаем:** в `web_app/next.config.ts` выставить `devIndicators: false` (Next 15 синтаксис). Проверить, что и `buildActivity`, и `appIsrStatus` индикаторы скрыты.
- **Acceptance:** `npm run dev` → в левом нижнем углу нет иконки Next.js ни в одном маршруте.
- **Deps:** —.

---

### P0-2. Переименования вкладок (без рестракта)
- **Источник запроса:** часть 5, часть 6, часть 8.
- **Effort:** S.
- **Risk:** low (одна правка `web_app/lib/navigation.ts` + соответствующие h1/title в страницах).
- **Что делаем:**
  1. «Обзор» → «Брифинг» (`/daily-summary`).
  2. «Рабочие списки» → «Задачи» (`/worklists`).
  3. «Животные» → «Стадо» (`/profiles/animal`).
  4. Убрать пункт «Лечение / каренция» из сайдбара (маршрут пока сохранить — он будет вложен в Ветеринарию на P1-3).
- **Acceptance:** sidebar показывает новые названия; `tests/navigation.test.ts` обновлён; deep-links (старые URL) продолжают работать (никаких редиректов не вводим, просто меняем label).
- **Deps:** —.

---

### P0-4. Cleanup: убрать дубль `src/<pkg>/` vs top-level `<pkg>/` для web_cabinet и genomeai
- **Источник запроса:** обнаружено при выполнении P1-1b (2026-05-12). Я отредактировал legacy-копию `src/web_cabinet/api_boundary_v1.py`, потратил время на отладку 404, потом нашёл, что runtime импортирует `/opt/genomeai/repo/web_cabinet/` (top-level), а не `/opt/genomeai/repo/src/web_cabinet/`.
- **Effort:** S → M (зависит от выбранной стратегии).
- **Risk:** med (любая ошибка в раскладке пакетов сломает рантайм; нужны прогоны всех 7 гейтов CLAUDE.md §4 на проверку).
- **Что констатируется (факт-чек):**
  - `pyproject.toml`: `[tool.setuptools] package-dir = {"" = "src"}` + `[tool.setuptools.packages.find] where = ["src"]`. **Декларация: канонический корень = `src/`**.
  - **Runtime-импорты** (`python -c "import web_cabinet; print(__file__)"`):
    - `web_cabinet` → `/opt/genomeai/repo/web_cabinet/__init__.py` (top-level, **не** канонический по pyproject).
    - `genomeai`   → `/opt/genomeai/repo/genomeai/__init__.py` (top-level, **не** канонический по pyproject).
    - `core`       → `/opt/genomeai/repo/src/core/__init__.py` (канонический, дубля нет).
  - `diff -r --brief web_cabinet/ src/web_cabinet/` показывает **20+ различающихся файлов** (без `__pycache__`). Размер: top-level `api_boundary_v1.py` = 1478 строк, src = 948 — top-level содержит более новые endpoint'ы (insights, qc, uploads, timeline), которых нет в src.
  - **Вывод:** top-level — это фактический runtime, src — стейл-копия от какой-то более старой реорганизации.
- **Что делаем (две стратегии, выбирает координатор):**

  **Стратегия A — "Согласовать с pyproject" (медленнее, чище):**
  1. Перенести все актуальные правки из `web_cabinet/` в `src/web_cabinet/`, аналогично для `genomeai`.
  2. Удалить top-level `web_cabinet/` и `genomeai/` (после переноса).
  3. Прогнать `pip install -e .` чтобы установить пакеты из `src/`.
  4. Прогнать 7 гейтов CLAUDE.md §4. Особое внимание smoke-тестам и golden.
  5. Если что-то ссылается на `web_cabinet/` напрямую (например, скрипты, тестовые fixtures, docker COPY) — переписать пути.
  - **Плюс:** один источник правды, как заявлено в pyproject.
  - **Минус:** L-объём, риск регрессий, нужны все 7 гейтов.

  **Стратегия B — "Зафиксировать факт" (быстрее, прагматичнее):**
  1. Удалить **стейл-копию** `src/web_cabinet/` и `src/genomeai/` (или переименовать в `_archive_*` для истории).
  2. Обновить `pyproject.toml`: `package-dir` снять (или явно установить `{"" = "."}`), `where = ["."]`.
  3. Обновить CI/install-инструкции, если они опираются на `src/` layout.
  4. Прогнать гейты.
  - **Плюс:** S-объём, без рисков для runtime.
  - **Минус:** уходим от каноничного python-src layout (но проект и так от него ушёл де-факто).
- **Acceptance:** для обеих стратегий — `find . -type d -name "web_cabinet" -not -path "*/node_modules/*" -not -path "*/__pycache__*"` возвращает **ровно одну** директорию (то же для genomeai). 7 гейтов CLAUDE.md §4 зелёные. Документация (`docs/project_map.md`) обновлена под выбранную раскладку.
- **Deps:** ничего не блокирует; **рекомендую сделать до начала P1-1c**, иначе frontend-склейка может ткнуться в новые баги при правках endpoint'ов.
- **Промежуточная mitigation (если решим отложить):** добавить в CLAUDE.md §5 явную пометку «`web_cabinet` и `genomeai` имеют дубль; редактировать ТОЛЬКО `/opt/genomeai/repo/web_cabinet/` и `/opt/genomeai/repo/genomeai/` — это runtime. `src/web_cabinet/` и `src/genomeai/` — стейл-копия, не трогать». Это убережёт людей и ИИ-ассистентов до настоящего cleanup'а.

---

### P0-3. Привести страницы «Решения» и «Готовность системы» к канону (если ещё не приведены)
- **Источник запроса:** в наблюдении 468 уже сделано — **верифицировать**, что соответствует общесистемному UI (как в Decisions/Readiness redesign от 2026-05-09).
- **Effort:** S (только аудит).
- **Risk:** low.
- **Acceptance:** скрин-обход и сравнение с `docs/design_reference/`.

---

### P1-1. «Брифинг»: всплывающее окно с настройщиком + расписание + автозадачи
- **Источник запроса:** часть 5.
- **Effort:** M.
- **Risk:** low (frontend + один новый эндпоинт настроек).
- **Что делаем:**
  1. На странице `/daily-summary` рядом с «Создать брифинг» добавить кнопку **«Настроить брифинг»** и **«История брифингов»**.
  2. «Настроить брифинг» открывает модалку, которая внутри ререндерит существующие `create-brief-card` + `settings-card` + переключатели:
     - периодичность (раз в день / неделю / месяц) и время;
     - переключатель «ставить задачи автоматически» vs «требует подтверждения».
  3. «История брифингов» — модалка/выезжающая панель поверх существующего `past-briefings-list`.
  4. Backend: новый эндпоинт `GET/PUT /api/v1/briefing/schedule` (хранить в `src/core/workflow/` или соседнем модуле; добавить в `public_interfaces.json`).
- **Acceptance:** schedule сохраняется, audit-event пишется (см. CLAUDE.md §3 «привилегированное действие — audit-logged»); ручной smoke: открыл модалку, сохранил расписание, обновил страницу — состояние сохранилось.
- **Deps:** P0-2 (переименование).

---

### P1-2. Инсайты → автогенерация задач с редактором и кнопкой постановки
- **Источник запроса:** часть 6.
- **Effort:** L.
- **Risk:** med (трогаем RBAC: `tasks.manage` и `alerts.manage`, нужен audit-log на постановку задач).
- **Что делаем:**
  1. **Backend:** существующий инсайт-движок → построитель `RecommendedTask` (description, due_at?, priority, assignee_role|assignee_user_id), привязанный к `insight_id`. Контракт в `packages/contracts/`.
  2. **Frontend:** на `/insights` добавить блок «Рекомендованные задачи» — список с inline-редактором (4 поля) и кнопками «удалить» / «поставить».
  3. Кнопка «Поставить задачи» → POST `/api/v1/worklists/from-insights` (массовая постановка) → задачи появляются на `/worklists` (теперь «Задачи»).
  4. На странице Задачи (`/worklists`) — каждая задача показывает свой `insight_id` со ссылкой на источник.
  5. **UI Задач** — провести через тот же шаблон, что Decisions/Readiness (`docs/design_reference/`).
- **Acceptance:** инсайт → задача → выполнение, с двусторонней навигацией; integration-тест на end-to-end путь.
- **Deps:** P0-2.

---

### P1-3. Стадо: раскрывающаяся секция + объединение Воспроизводство/Ветеринария/Кормление
- **Источник запроса:** часть 8.
- **Effort:** L.
- **Risk:** med (UI рестракт + новая вкладка Кормление).
- **Что делаем:**
  1. В `navigation.ts` ввести **группу-аккордеон** «Стадо» с подпунктами: Животные, Воспроизводство, Ветеринария, Кормление.
  2. Маршрут `/treatments` сделать вложенным внутри `/vet` (например, отдельный таб «Каренция» внутри Ветеринарии). Сохранить старый URL как редирект.
  3. Создать `/feeding` — минимальный каркас, конкретику собирать с координатором (см. «От координатора»).
  4. На страницах Ветеринария и Воспроизводство — секция «Задачи по направлению», тянущая из `/worklists` по фильтру `category in (vet, repro)`.
- **Acceptance:** сайдбар разворачивается/сворачивается, deep-links работают, задачи действительно показываются и обновляются.
- **Deps:** P0-2, P1-2 (для секции «Задачи»).

---

### P1-4. Новая вкладка «Команда»
- **Источник запроса:** часть 7.
- **Effort:** L.
- **Risk:** med (новые персональные данные: ФИО, фото, должность → нужен RBAC `personnel.read/manage` + GDPR-аналог в audit).
- **Что делаем:**
  1. Backend-модель `Personnel` (id, full_name, position, group_id, photo_ref). Миграция Alembic + endpoint `/api/v1/personnel`.
  2. UI `/team` по аналогии с `/profiles/animal`: переключение «по группам / по ФИО»; карточка сотрудника = ФИО, фото, должность, **личные задачи** + **задачи группы** (data — из `/worklists`).
  3. FAB (см. `components/app/fab.tsx`) — на странице Команда добавить пункт «Поставить задачу», открывает модалку с выбором сотрудник/группа.
  4. Зашить роль/сотрудника в `RecommendedTask.assignee` из P1-2.
- **Acceptance:** карточка отображает задачи в реальном времени; FAB действительно создаёт задачу на `/worklists`.
- **Deps:** P1-2 (задачная модель должна знать assignee).
- **Прогресс на 2026-05-15:**
  - ✅ P1-4a (model + migration + endpoint) — закрыт коммитами `0786756…6338d17` (RBAC, contracts, domain, alembic 20260515_17, PersonnelRepo, GET/POST endpoints с PII-маскингом и audit).
  - ⏸ Photo upload через MinIO — **отложен** (P1-4a-7). MinIO в локальном dev-контуре не поднят; `photo_ref` принимается endpoint'ом как строка, реальная заливка вернётся когда MinIO будет живым (вероятно в составе P1-6 «Контроль интеграций»).
  - ✅ P1-4b (UI `/team`) — закрыт коммитами `8152230…a97b4e8` (skeleton, PersonnelSurface, user_id soft-FK, PersonnelDetail drawer).
  - ✅ P1-4c-1 (POST `/worklists`) — закрыт коммитом `ee4482c` (backend, audit `tasks.create.manual`).
  - ✅ P1-4c-2 (TaskCreateModal + FAB на `/team`) — закрыт коммитами `a42e6c4` (контракты/клиент/валидация), `6e5117f` (модалка), `ff92646` (FAB + интеграция + Playwright smoke). R10 решён через декаплинг полей: `assignee_team` отдельно из catalog, `owner_user_id` отдельно из personnel; `personnel.group_id` остаётся free-form info-полем.
  - ✅ P1-4d (PATCH/DELETE на `/personnel`) — закрыт коммитами `d187e32` (backend workflow + endpoints + audit), `199f0d1` (TS-клиент, edit-модалка, delete-confirm, интеграция в drawer + UI smoke). Hard delete с before/after_json в audit_log. Бонусом починен latent proxy bug — `NextResponse` крашился на 204-ответах.
  - ✅ **P1-4 R-debt quick-wins** (2026-05-15) — коммиты `40a8a76` (R14 backend `?has_user=true`), `7f64367` (hotfix `_decode_task_row` для JSONB dict), `d0aeaad` (R12 owner-filter + R13 worklists refetch + ?has_user=true в TaskCreateModal). Drawer теперь обновляется в реальном времени после создания задачи.
  - ➡ Следующий шаг: либо оставшиеся P1-4 R-debt (R6 MinIO photo, R7 user-mapping UI, R16 orphan tasks, R19 auth-aware user_id picker), либо P1-5 slice 4 IAM editing (high-risk), либо переход к P2.

---

### P1-5. Администрирование: канон UI + IAM-матрица + точки входа
- **Источник запроса:** часть 9.
- **Effort:** L.
- **Risk:** **high** (RBAC матрица — критичная зона, CLAUDE.md §7 «RBAC ослаблять нельзя»).
- **Что делаем:**
  1. UI `/admin` приводим к канону (как Decisions/Readiness).
  2. Кнопки-плитки: **AI-наблюдаемость** (`/admin/ai`), **Логи системы**, **Логи безопасности**, **Grafana** (внешняя ссылка из конфига), **Обучение ИИ-моделей** (новый раздел `/admin/ai/training`), **Контроль интеграций** (`/admin/integrations`, см. P1-6).
  3. **IAM-матрица** — интерактивная: ось пользователи / ось permissions из `src/core/security/`. Чекбоксы вкл/выкл с обязательным `audit_event` на каждое изменение + подтверждение через двухкликовое UI.
  4. Защита: только роль `admin` (RBAC проверка на бэкенде, не только UI).
- **Acceptance:** изменение permission → видно в `auth_audit` логах; пользователь без admin не видит и не вызывает endpoint; e2e-тест на отказ.
- **Deps:** P0-3, согласование политики с координатором (см. «От координатора»).
- **Прогресс на 2026-05-15:**
  - ✅ P1-5 slice 1 — `/admin` tile canon (`8cc35c6`): 5 плиток (IAM, AI, Observability, Readiness, Support). Decision: только existing routes, без заглушек на P1-6 / training (отдельные эпики).
  - ✅ hotfix (`4952341`): `list_roles` / `get_permissions_for_role` fallback при отсутствии optional `roles` / `role_permissions` таблиц; включая `conn.rollback()` чтобы не ловить `InFailedSqlTransaction`.
  - ✅ P1-5 slice 2 — `/admin/iam` read-only matrix (`bc50ae0`): table 8 ролей × 5 actions с disabled-чекбоксами; sticky-headers; explainability block.
  - ✅ P1-5 slice 3a — миграция `role_permissions_overrides_v1` (`48e3edd`): PK (role, permission), CHECK effect IN ('grant', 'revoke'), audit-friendly columns.
  - ✅ P1-5 slice 3b — backend (`fe1af0b`): PATCH endpoint с effect=grant|revoke|clear, audit `iam.permission.{grant|revoke|clear}`, RBAC `admin.manage` (новая permission), validation против ALL_PERMISSIONS и list_roles. Effective merge встроен в `get_permissions_for_role`.
  - ✅ Slice 5 docs: T34-P1-5_risks_and_assumptions.md + public_interfaces.json (PATCH добавлен).
  - ⏸ **P1-5 slice 4 — UI editing + 2-click confirm — ОТЛОЖЕН** по соглашению с координатором. Текущее состояние UI = read-only безопасно. Рисков-долг по edit-UX и admin.manage lock-out (R4 в risks-доке) требует отдельного согласования прежде чем включать interactive editing.
  - ✅ **P1-5 R-debt quick-wins** (2026-05-15) — коммит `6f63491` закрывает R6 (backend hard-guard «нельзя revoke admin.manage у Admin», HTTP 400 `iam.lock_out_protected`) и R7 (audit before_json = предыдущий effect override при повторных PATCH).
  - ➡ Следующий шаг: либо открыть P1-5 slice 4 отдельной итерацией с продуманным confirm-flow, либо перейти к другому эпику (P1-3 «Стадо», P1-6 «Интеграции», R-фолоу-апы из P1-4).

---

### P1-6. Контроль интеграций — централизованная панель на админке
- **Источник запроса:** дозапрос от 2026-05-12.
- **Effort:** M (frontend page + агрегирующий backend-эндпоинт).
- **Risk:** med (показывает статус *всех* внешних соединений, включая ПДн-источники и токены — нужен RBAC).
- **Что делаем:**
  1. **Backend:** новый endpoint `GET /api/v1/integrations/health` — агрегатор, который опрашивает каждый зарегистрированный коннектор и возвращает унифицированный массив:
     ```
     [{ id, name, kind, status: ok|degraded|down|disabled, last_sync_at,
        records_in_last_window, error_count, last_error, latency_ms }, ...]
     ```
     Источники, которые входят в агрегат на старте:
     - **IoT-источники** (P2-3): ошейники, болюсы, бирки, весы, камеры — по каждому типу/вендору отдельная строка.
     - **RU-системы** (P2-4): Селекс, 1С:Зоотехния, Хэрриот.
     - **LLM-провайдер** (P2-2): OpenAI / Ollama — текущий active provider + статус последнего запроса.
     - **Существующие коннекторы** из `src/genomeai/connectors_v1.py` и `docs/farm_connector_catalog.md` (`selex_basic`, `selex_batch`, `1c`, api_stub-ы и др.).
     - **Sensor ingestion API** (`docs/integrations/sensor_ingestion_api.md`).
  2. **Контракт:** `packages/contracts/integrations_health_v1.ts` + Python-equivalent в `src/core/interoperability/`. Зарегистрировать в `docs/public_interfaces.json`.
  3. **Frontend:** новая страница `/admin/integrations`, доступная только под permission `integrations.view`. На странице:
     - Таблица всех интеграций со статусами в реальном времени (auto-refresh раз в 30s).
     - Per-row детализация (expand): последние N ошибок, маппинг-конфиг (read-only, без секретов), счётчики.
     - Кнопки действий на каждом коннекторе: **«Запустить синхронизацию сейчас»**, **«Включить/выключить»**, **«Открыть логи»** (deep-link в `/admin/logs?source=<connector_id>`).
     - **Все действия требуют permission `integrations.manage`** и пишутся в audit-log (CLAUDE.md §3).
  4. **Плитка на `/admin`** — добавлена в P1-5; визуально подсвечивает агрегатный статус (зелёный/жёлтый/красный) — берётся из того же endpoint.
  5. **Секреты** — на странице не отображаем, никаких токенов/паролей в payload health-эндпоинта. Только статус и метаданные.
  6. **Интерфейс расширения:** каждый коннектор реализует Python-протокол `IntegrationHealthProvider` (метод `get_health() -> IntegrationHealth`). Новые коннекторы (например, фазы IoT и RU) подключаются через регистрацию в `src/core/interoperability/registry.py`, без правки самой страницы.
- **Acceptance:**
  - Открыл `/admin/integrations` — вижу все известные системе интеграции, у каждой есть статус и last_sync_at.
  - Нажал «Запустить синхронизацию» — в audit-log появилась запись `integration.manual_sync`, в логах коннектора видно запуск.
  - Пользователь без `integrations.view` получает 403 на endpoint и не видит плитку на `/admin`.
  - Тест: namespaced contract test, что любой новый коннектор обязан имплементировать `IntegrationHealthProvider` (иначе CI падает).
- **Deps:**
  - **Минимум** — P1-5 (плитка должна куда-то встать, и общесистемный UI каноном).
  - **Полезно** — после P2-2/P2-3/P2-4, чтобы агрегат был содержательным; **но** сам каркас (endpoint + страница) можно строить заранее — он сразу покажет существующие `connectors_v1.py` коннекторы.
- **Заметка:** не путать с `/connections` — там пользователь *настраивает* интеграции (per-tenant), а `/admin/integrations` — это *системный надзор* для админа (cross-tenant, диагностика, ручной запуск).
- **Прогресс на 2026-05-15:**
  - ✅ P1-6 slice 1 — backend (`39f5ed0`): contract `IntegrationHealth`, Protocol-based registry, 5 bundled providers (LLM / connectors_v1 / IoT stubs / sensor stub / RU stubs), endpoint `GET /api/app/v1/integrations/health` gated by `integrations.view`, 7/7 unit tests pass. Live smoke: 15 rows across 5 kinds.
  - ✅ P1-6 slice 2 — frontend (`7c3b218`): `/admin/integrations` page with grouped table, status badges, expand-rows, auto-refresh 30s, aggregate status в topbar. 6-я плитка на `/admin`.
  - ✅ Slice 3 — docs: T34-P1-6_risks_and_assumptions.md + public_interfaces.json (PATCH добавлен → GET integrations/health добавлен) + backlog progress.
  - ⏸ **P1-6b — action layer (manual sync / enable-disable / deep-link logs) — ОТЛОЖЕН.** Текущее состояние = read-only безопасное. R1 (LLM ping) остаётся открытым для будущей итерации.
  - ✅ **P1-6 R-debt quick-wins** (2026-05-15) — коммит `73a597f` закрывает R3 (`get_health(conn, *, tenant_id)` — endpoint пробрасывает user.tenant_id) и R6 (`PERM_INTEGRATIONS_VIEW` добавлен в `DEFAULT_ROLE_PERMISSIONS[Director]`).
  - ➡ Следующий шаг: P1-tails (P1-5 slice 4 IAM editing + R-фолоу-апы P1-4/P1-5), либо переход к P2.

---

### P2-1. Экономика — переосмыслить и переделать
- **Источник запроса:** часть 11.
- **Effort:** L → XL (зависит от scope).
- **Risk:** med (контрактные изменения, экономика влияет на отчёты).
- **Что делаем:**
  1. Сначала **discovery-итерация** (1–2 дня): аудит того, что страница `/economics` сейчас показывает, какие данные у нас в `src/core/reporting/` и `docs/economics_pandas_stability.md`, что хочет видеть пользователь.
  2. Артефакт discovery — отдельный RFC `docs/iterations/T34-economics-rfc.md` с конкретным макетом и контрактом.
  3. Только после approve — переход к implementation в инкрементах.
- **Acceptance discovery:** RFC утверждён координатором.
- **Deps:** —.

---

### P2-2. Локальный ИИ на Ollama (миграция с OpenAI)
- **Источник запроса:** часть 10.
- **Effort:** XL.
- **Risk:** high (трогаем все consumers AI: брифинг, инсайты, ассистент; меняем deps в `pyproject.toml`; нужен offline-режим).
- **Что делаем (порядок):**
  1. **Discovery / выбор модели:** прогнать `llama3.1:8b-instruct`, `qwen2.5:7b-instruct`, `mistral-nemo:12b` на наших фактических промптах. Бенчмарк по latency / qualitative score / RU-fluency. Артефакт — `docs/iterations/T34-ollama-rfc.md` с обоснованием выбора.
  2. **Абстракция LLM-клиента:** ввести `src/core/llm/provider.py` с интерфейсом `generate(prompt, ...) -> str`. Заменить прямые импорты `openai` в `regular_reporting.py` и `assistant_reporting.py`.
  3. **Ollama-провайдер:** HTTP-клиент к `http://ollama:11434`. Конфигурация через `GENOMEAI_LLM_PROVIDER=ollama|openai|disabled`, `GENOMEAI_LLM_MODEL=...`, `GENOMEAI_LLM_BASE_URL=...`.
  4. **Compose:** добавить `ollama` сервис в `deploy/adult/compose.yaml` (НЕ в `compose.prod.yaml` без согласования — там `read_only`).
  5. **Compatibility path:** оставить OpenAI как fallback по `docs/deprecation_policy.md`, по умолчанию в prod = ollama.
  6. **Тесты:** все тесты, которые ждали OpenAI, должны уметь работать с мок-провайдером.
- **Acceptance:** smoke `genomeai smoke` + ассистентский эндпоинт работают без `OPENAI_API_KEY`, при `GENOMEAI_LLM_PROVIDER=ollama` ответы приходят локально.
- **Deps:** —. Можно вести **параллельным треком** с P1 (никаких UI-блокеров).

---

### P2-3. IoT-интеграция (ошейники, болюсы, бирки, весы, камеры)
- **Источник запроса:** часть 12.
- **Effort:** XL (эпик на несколько спринтов).
- **Risk:** high (новые внешние интерфейсы, ингест-pipeline, влияние на инсайты и QC).
- **Что делаем (фазированно):**
  1. **Discovery / каталог источников:** для каждого класса (collar / ear-tag / bolus / leg-band / smart-scale / camera) — перечень реальных вендоров и форматов (CSV / MQTT / Webhook / RTSP). Артефакт: `docs/integrations/iot_device_catalog.md`.
  2. **Канонический ingest-контракт:** расширить `docs/integrations/sensor_ingestion_api.md` до vendor-neutral payload (`device_id`, `device_type`, `animal_ref`, `metric`, `value`, `ts`, `quality_flag`).
  3. **Storage layer:** новая Postgres-таблица `iot_observations` + partitioning по дате (см. CLAUDE.md §7 — adult/prod без SQLite).
  4. **Demo simulator:** отдельный worker, генерирующий поток событий для пилотов. Фича-флаг `GENOMEAI_IOT_DEMO=true`.
  5. **Frontend integrations:**
     - Карточка животного (`/profiles/animal/[id]`) — табы «Ошейник / Болюс / Весы / Браслет / Камеры».
     - Лента событий — IoT-аномалии как отдельный класс событий.
     - Аналитика/QC — overlay IoT-метрик на графики.
     - Инсайты — правила, которые потребляют IoT-данные.
  6. **Graceful degradation:** UI явно различает «нет устройства» / «устройство есть, данных нет» / «есть данные».
- **Acceptance:** демо-режим показывает живой поток в UI на пилоте; staging-режим принимает реальные данные одного вендора.
- **Deps:** **сильная связка с P1-2 (инсайты) и P1-3 (Стадо).** Делаем после того, как UI-каркас Стада стабилизируется.

---

### P2-4. Интеграции с российскими системами: Селекс, 1С:Зоотехния, Хэрриот
- **Источник запроса:** дозапрос от 2026-05-12.
- **Effort:** XL (эпик, 3–5 спринтов суммарно; делится на 3 поддорожки).
- **Risk:** high (внешние системы, регуляторика — особенно Хэрриот/Ветис; ПДн в выгрузках; контрактные изменения).
- **Что уже есть (baseline):**
  - CSV-импорт инструкции: `docs/pilot_onboarding/02_csv_export_selex.md`, `03_csv_export_1c_livestock.md`.
  - Маппинг-шаблоны: `configs/mappings/templates/selex/*.yaml`, `configs/mappings/templates/1c/*.yaml`.
  - Legacy-импорт адаптеры: `src/core/interoperability/legacy_import.py`, `parallel_run.py`.
  - Каталог коннекторов: `docs/farm_connector_catalog.md` (упоминание `selex_batch`, `selex_basic`).
  - **Хэрриот — НИЧЕГО НЕТ**, нужно с нуля.
- **Что делаем (фазированно):**

  **Фаза 0 — Discovery (общая, обязательная перед всеми тремя дорожками):**
  1. Аудит, что **именно** работает из существующего Селекс/1С baseline: запустить existing CSV-import на эталонной выгрузке и зафиксировать gaps.
  2. Каталог сущностей-кандидатов на синхронизацию: animal, lactation, milking, repro_event, vet_event, group, weighing, drug_treatment.
  3. Артефакт: `docs/iterations/T34-ru-integrations-rfc.md` с decision-matrix (CSV/API, push/pull, частота, конфликт-резолвинг).

  **Дорожка A — Селекс (Селэкс, ПЛИНОР):**
  1. Фаза 1: upgrade существующего CSV-импорта до **production-grade** (полные маппинги для версий 7.x и 8.x, инкрементальные выгрузки по дате, дедупликация по `tag_id`).
  2. Фаза 2: backwards-only sync (Селекс → GenomeAI) через **planned-drop folder** (агент на стороне фермы кладёт CSV в shared volume, GenomeAI watcher подхватывает).
  3. Фаза 3 (опционально, по запросу пилотов): прямой коннектор к БД Селекса (Firebird/Sybase в зависимости от версии) — only если CSV-режим неприемлем у пилота. Требует RFC.
  4. UI: на странице `/connections` карточка «Селекс» → статус последней синхронизации, lag, отвергнутые строки с причинами.

  **Дорожка B — 1С: Зоотехния и племенное дело:**
  1. Фаза 1: upgrade CSV-импорта (как для Селекса).
  2. Фаза 2: интеграция через **штатный REST/OData интерфейс 1С:Предприятия 8.3** (он есть из коробки в конфигурациях 8.3+). Маппинг сущностей `Справочник.Животные`, `Документ.КонтрольнаяДойка`, `Документ.ВетеринарноеМероприятие` → наш канонический контракт.
  3. Аутентификация: basic auth с сервисным пользователем 1С, секрет через `*_FILE` (CLAUDE.md §7 Secrets).
  4. Двусторонняя синхронизация (фаза 3) — **только после approve координатора**, т.к. меняет данные в системе учёта фермы.
  5. UI: карточка «1С:Зоотехния» на `/connections` с тестом подключения, выбором базы, периодичностью poll.

  **Дорожка C — Хэрриот (ФГИС ВетИС, выписка ВСД):**
  1. Хэрриот — это **региональная** надстройка над ФГИС ВетИС (Меркурий). У него есть свой API (документация Россельхознадзора), но доступ — через сертификаты УЦ Россельхознадзора.
  2. Фаза 1: discovery — какие именно операции нужны (выписка ВСД, регистрация перемещения, импорт справочника животных, выписка лечебных мероприятий). Артефакт — отдельный RFC, т.к. регуляторика.
  3. Фаза 2: реализация **read-only** клиента: импорт справочника животных и истории ВСД в карточку животного.
  4. Фаза 3 (под запрос): выписка ВСД из GenomeAI — write-операции, требуют подписи и юр.основания. **Делаем только после явного approve координатора + юриста.**
  5. Секреты: токены/сертификаты — через `*_FILE` mount, никаких plain-text в compose.
  6. UI: карточка «Хэрриот» на `/connections` + блок в карточке животного «Документы Хэрриот / ВСД».

  **Общие требования по всем трём дорожкам:**
  - Каждая интеграция = **отдельный коннектор** в `src/core/interoperability/connectors/<system>/`, не правим монолит.
  - Любой импорт/экспорт = audit-event (CLAUDE.md §3).
  - Маппинги — декларативные (YAML в `configs/mappings/`), а не хардкод.
  - Конфликт-резолвинг: записи из внешних систем имеют `source_system` и `source_record_id`; повторный импорт того же record_id = upsert, не дубль.
  - Поддержка **частичной** интеграции: ферма может включить только Селекс, или только Хэрриот, или комбинации.
  - Все три интеграции должны кооперироваться с IoT (P2-3): данные из ошейника не должны затирать данные из 1С, и наоборот — приоритезация по `source_system_priority` в конфиге.
- **Acceptance (на эпик в целом):**
  - На пилоте подключены **хотя бы две** системы из трёх, синхронизация идёт в фоне, статус виден в `/connections`.
  - Карточка животного показывает merge-данные с пометкой источника каждого поля.
  - `audit_event` пишется на каждый sync-цикл.
- **Deps:**
  - **Фаза 0 (discovery)** можно начинать сразу.
  - Production-внедрение дорожек A и B — после P1-3 (Стадо реструктурирован), чтобы карточки животных были готовы принимать merge-данные.
  - Дорожка C (Хэрриот) — после P1-3 и P1-5 (RBAC матрица), т.к. требует тонких permissions.
  - Хорошо ложится **параллельно с P2-3 (IoT)**, т.к. обе задачи строят source-of-record слой.

---

## 3. Предлагаемый порядок выполнения (sprint-разбивка)

| Sprint | Содержимое | Длительность | Готовность |
|--------|------------|--------------|------------|
| **S1** (текущий) | P0-1, P0-2, P0-3, P0-4 | ≤3 дней | сайдбар + dev-overlay + одно дерево пакетов (web_cabinet/genomeai) |
| **S2** | P1-1 (Брифинг), P1-2 (Инсайты → Задачи) | 1–1.5 недели | живая связка инсайтов и задач |
| **S3** | P1-3 (Стадо аккордеон), P1-4 (Команда) | 1.5–2 недели | новые секции в навигации |
| **S4** | P1-5 (Админка + IAM), P1-6 (Контроль интеграций) | 1.5 недели | админ-консоль + матрица доступов + панель статуса коннекторов |
| **S5** | P2-2 (Ollama) — параллельным треком к S2–S4 | 2–3 недели | локальный LLM в adult |
| **S6** | P2-1 (Экономика RFC → implementation) | 2–3 недели | новая Экономика |
| **S7+** | P2-3 (IoT эпик, фазами 1–6) | 4–6 недель | demo-режим → реальная интеграция |
| **S7+ (параллельно)** | P2-4 (RU-интеграции: Селекс/1С/Хэрриот) — фаза 0 общая, далее по дорожкам A/B/C | 4–6 недель | хотя бы 2 системы из 3 синхронизированы на пилоте |

---

## 4. Что нужно от координатора (блокирующее)

1. **P0-2 / Лечение:** подтверди, что URL `/treatments` оставляем как редирект, а не полный delete (есть ли внешние ссылки в обучающих материалах).
2. **P1-3 / Кормление:** какой минимальный набор данных мы готовы показать на старте? (рацион / TMR / отказ от корма / групповая статистика).
3. **P1-4 / Команда:** какие поля «персонала» обязательны? Готовы ли мы хранить фото в Postgres или это `MinIO/S3`? Юр.основание (особенно ПДн).
4. **P1-5 / IAM:** даём ли мы в UI «изобретать» новые permissions, или матрица только включает/выключает существующие из `src/core/security/`?
5. **P2-2 / Ollama:** есть ли железо под GPU-инференс (для 12B+ моделей), или ограничиваемся 7–8B?
6. **P2-3 / IoT:** список реальных вендоров в первых пилотах? (это сразу сужает каталог в фазе 1).
7. **P2-4 / RU-интеграции:** какие пилоты уже используют Селекс / 1С / Хэрриот — это определит, с какой дорожки стартуем. Готовы ли мы инвестировать в УЦ-сертификаты Россельхознадзора для дорожки C?
8. **P1-6 / Контроль интеграций:** разделение `/admin/integrations` (системный надзор, cross-tenant, ручной запуск) и `/connections` (пользовательская настройка per-tenant) — ОК, или объединяем в одну страницу с режимами просмотра? Если разделение ОК — нужны два разных permission (`integrations.view`/`integrations.manage` vs существующий доступ к `/connections`).

---

## 5. Риски и допущения по бэклогу

- Приоритеты выше — **предложение**, не приказ. Если P2-2 (Ollama) надо делать первым (например, под демо без интернета), сдвигаем порядок и явно записываем это сюда.
- Все эпики P2 требуют отдельных RFC и собственных gate-прогонов перед `proven` (7 гейтов из CLAUDE.md §4).
- Любая правка `golden/scenarios/` — отдельный коммит с маркером `golden-update:` (CLAUDE.md §6).
- Если по ходу появятся новые задачи от координатора — дописываем в этот же файл, секциями `P0-N` / `P1-N` / `P2-N` без перенумерации существующих.

---

**Итог:** ничего не реализовано, это backlog. Готов начинать с **P0-1 + P0-2** в ближайший инкремент, как только получу ответ на блокирующие вопросы выше (для P0 ответы не нужны — можно стартовать сразу).

# Полная функциональная проверка через UI — Web

Дата: 2026-04-14  
Статус: подробный manual для QA / implementation / customer UAT.

Этот документ описывает **пошаговую проверку web-приложения** `web_app` по ролям и сценариям. Он не заменяет backend smoke, а дополняет его. Проверка должна выполняться **после** успешного развёртывания по `docs/deployment_full_guide.md` и базового ops smoke из `docs/operations_runbook.md`.

> Важно: этот manual сознательно **не придумывает UI-функции, которых нет**. Если поток в React реализован как foundation / read parity / preview parity, это отдельно помечено.

---

## 1. Что считается объектом проверки

Проверяется новый web frontend `web_app`, который после T32-12/T32-12A является **единственным продуктовым web UI**. Streamlit-контур уже удалён, а отсутствие legacy tails подтверждается gate/validator-артефактами пост-удаления.

Проверяемые крупные контуры:

- auth / role access / navigation
- daily summary / alerts / worklists / planner
- animal profile / group profile
- reports / report governance
- assistant / explainability / decision intelligence
- reproduction / vet / treatments
- economics / what-if
- support / incident / readiness / pilot / observability / admin

Системные ограничения, которые надо учитывать во время UAT:

- **Daily brief** в React — это **preview parity**, а не обещание полного replacement более широкого historical daily-brief процесса.
- **Admin page в React** — это **command center / permission matrix preview / readiness hooks**, но не полноценный user CRUD кабинет.
- **Assistant в React** остаётся thin frontend: он только передаёт контекст в backend boundary и не должен создавать собственную explainability-логику.

---

## 2. Предварительные условия

### 2.1. Развёртывание и health

Перед UI-проверкой должны быть зелёными:

1. `bash scripts/smoke_t32_10_server_deployment.sh`
2. `bash scripts/smoke_t32_10a_production_security.sh`
3. `bash scripts/smoke_t32_13_deployment_full_guide.sh`

Минимальные runtime-checks:

- reverse proxy отвечает по основному URL;
- `/api/healthz` и `/api/readyz` backend доступны через ingress;
- `web_app` отдаёт `/login`;
- backend `/api/app/v1/*` отвечает без 5xx;
- demo data или customer UAT dataset уже загружены.

### 2.2. Данные для проверки

Рекомендуемый baseline для UAT — синтетический демо-набор:

- `data/demo/demo_farm_v1/demo_farm_manifest.json`
- `default_data_version = dv_demo_farm_v1`
- farms: `DEMO_FARM_001`, `DEMO_FARM_002`
- sites: `DEMO_SITE_001`, `DEMO_SITE_002`, `DEMO_SITE_003`

Полезные object IDs для ручной проверки:

- animal profile: `DEMO_COW_1002`
- animal profile (vet): `DEMO_COW_2002`
- animal profile (milk quality): `DEMO_COW_3002`
- group profile: `PEN_N1_LACT` или `PEN_N2_REPRO`

Полезные demo артефакты:

- reports в `data/demo/demo_farm_v1/dm_reports.csv`
- alerts в `data/demo/demo_farm_v1/dm_alerts.csv`
- treatments в `data/demo/demo_farm_v1/dm_treatments.csv`

### 2.3. Тестовые пользователи

#### Вариант A — fresh DB с seed users

При инициализации `users_v2` в `src/core/infra/web_db.py` создаются default users:

- `admin / admin`
- `director / director`
- `operator / operator`
- `viewer / viewer`
- `zootech / zootech`
- `vet / vet`

Tenant по умолчанию: `default`.

#### Вариант B — demo users из synthetic dataset

В `data/demo/demo_farm_v1/demo_farm_manifest.json` и `dm_users.csv` есть логины:

- `demo_admin`
- `demo_director`
- `demo_operator`
- `demo_zootech`
- `demo_vet`

Пароли для этих demo users не считаются предустановленными. Если используется именно demo user set, сначала выполните reset password через internal admin/support surface или seed-step окружения.

---

## 3. Что запускать до ручной web-проверки

### 3.1. Foundation / parity smoke

Выполните:

```bash
bash scripts/smoke_t32_05_react_daily_operations.sh
bash scripts/smoke_t32_06_react_profiles_reports_assistant.sh
bash scripts/smoke_t32_07_react_extended_surface.sh
```

### 3.2. Post-removal / cleanup gate

Выполните:

```bash
bash scripts/smoke_t32_12_streamlit_removal.sh
bash scripts/smoke_t32_12a_streamlit_legacy_cleanup.sh
```

### 3.3. Что должен зафиксировать QA перед началом

Зафиксируйте в протоколе:

- URL web frontend
- data_version для UAT
- набор пользователей / ролей
- дата и время запуска проверки
- commit / release tag / build version
- environment profile: `dev` / `stage` / `prod`

---

## 4. Карта маршрутов web UI

| Контур | Route | Что должно быть видно |
|---|---|---|
| Login | `/login` | форма `Tenant / Username / Password` |
| Daily summary | `/daily-summary` | заголовок `Home / daily summary` |
| Alerts | `/alerts` | заголовок `Alerts` |
| Worklists | `/worklists` | заголовок `Worklists` |
| Planner | `/planner` | заголовок `Planner` |
| Reports | `/reports` | каталог отчётов |
| Report detail | `/reports/{dataVersion}/{reportVersion}` | detail view + governance panel |
| Assistant | `/assistant` | interactive target-resolution shell |
| Decisions | `/decisions` | decision trail |
| Animal profile | `/profiles/animal/{objectId}` | `Animal Profile` |
| Group profile | `/profiles/group/{objectId}` | `Group Profile` |
| Reproduction | `/reproduction` | `Reproduction` |
| Vet | `/vet` | `Vet queues` |
| Treatments | `/treatments` | `Treatments / withdrawal` |
| Economics | `/economics` | `Economics / what-if` |
| Support | `/support` | `Support / governance` |
| Pilot | `/pilot` | `Pilot evidence` |
| Readiness | `/readiness` | readiness checks |
| Observability | `/observability` | diagnostics / telemetry |
| Admin | `/admin` | admin command center |

---

## 5. Ожидаемая роль-ориентированная навигация

Проверяется по `web_app/lib/navigation.ts` и по фактическому меню в sidebar.

### 5.1 Admin

Ожидается доступ ко всем офисным и operational разделам, включая:

- `/daily-summary`
- `/alerts`
- `/worklists`
- `/planner`
- `/reproduction`
- `/vet`
- `/treatments`
- `/reports`
- `/assistant`
- `/decisions`
- `/economics`
- `/support`
- `/pilot`
- `/readiness`
- `/observability`
- `/admin`

### 5.2 Director

Ожидается фокус на:

- `/daily-summary`
- `/reports`
- `/assistant`
- `/decisions`
- `/economics`
- `/support` (если выданы permissions)
- `/pilot`, `/readiness` (если выданы permissions)

### 5.3 Operator / Zootech

Ожидается фокус на:

- `/daily-summary`
- `/alerts`
- `/worklists`
- `/planner`
- `/reproduction`
- `/reports`
- `/assistant`
- `/profiles/...`
- `/decisions`

### 5.4 Vet

Ожидается фокус на:

- `/daily-summary`
- `/alerts`
- `/worklists`
- `/vet`
- `/treatments`
- `/profiles/animal/...`
- `/assistant`
- `/reports`

### 5.5 Viewer / bounded external role

Ожидается ограниченный read-only доступ. Минимально проверить:

- логин проходит;
- в sidebar нет лишних write/governance surfaces, если permission не выдан;
- `/reports` доступен;
- `/support` может отсутствовать в меню;
- страницы decision/report governance не должны давать approve/reject/archive, если permissions не выданы.

> bounded external role в текущем web UI проверяется через тот же permission-driven механизм, что и `Viewer`. Если отдельная внешняя роль provisioned в окружении, сверяйте её меню и доступы с тем же сценарием, но фиксируйте фактические permission claims в отчёте UAT.

---

## 6. Пошаговые сценарии проверки — Web

Ниже каждый сценарий содержит:

- **Роли**
- **Предусловия**
- **Шаги**
- **Ожидаемый результат**
- **Pass / Fail критерий**
- **Smoke / evidence reference**

---

### WEB-AUTH-001 — Логин и базовая сессия

**Роли:** все  
**Предусловия:** пользователь создан, backend auth работает.  
**Шаги:**

1. Откройте `/login`.
2. Проверьте наличие полей `Tenant`, `Username`, `Password`.
3. Для fresh DB введите `default / admin / admin`.
4. Нажмите `Sign in`.
5. Убедитесь, что после входа происходит переход на `/dashboard`, который редиректит на `/daily-summary`.
6. В sidebar проверьте блок `Session`.
7. Нажмите `Refresh` и убедитесь, что сессия не теряется.
8. Нажмите `Sign out` и убедитесь, что происходит возврат на `/login`.

**Ожидаемый результат:**

- логин успешен;
- активна server-backed session;
- sidebar показывает `User`, `Role`, `Farm mode`;
- logout завершает сессию.

**Pass / Fail:**

- PASS: логин/логаут работают без 5xx и без ручной правки URL;
- FAIL: цикл login → protected routes → logout ломается.

**Reference:** T32-03/T32-04 auth foundation.

---

### WEB-RBAC-001 — Проверка меню по ролям

**Роли:** Admin, Director, Operator/Zootech, Vet, Viewer  
**Предусловия:** есть хотя бы один пользователь каждой роли.  
**Шаги:**

1. По очереди войдите под каждой ролью.
2. Зафиксируйте список route labels в sidebar.
3. Сверьте его с разделом 5 этого документа.
4. Для `Viewer` убедитесь, что не появляется лишний `Support`, если permission не выдан.
5. Для `Admin` убедитесь, что виден `Admin`.
6. Для `Vet` убедитесь, что видны `Vet queues` и `Treatments / withdrawal`.
7. Для `Operator/Zootech` убедитесь, что виден `Reproduction`.

**Ожидаемый результат:** меню сокращается/расширяется по permission set, а не одинаково для всех.

**Pass / Fail:**

- PASS: меню role-aware;
- FAIL: все роли видят одинаковое меню или роль не видит свой рабочий контур.

**Reference:** `web_app/lib/navigation.ts`, `web_app/tests/navigation.test.ts`.

---

### WEB-OPS-001 — Daily summary как стартовая рабочая точка

**Роли:** Director, Operator/Zootech, Vet, Admin  
**Предусловия:** данные и alerts/worklists/planner доступны через backend.  
**Шаги:**

1. Откройте `/daily-summary`.
2. Проверьте заголовок `Home / daily summary`.
3. Проверьте наличие карточек:
   - `Open alerts`
   - `Critical alerts`
   - `Open worklists`
   - `Overdue worklists`
   - `Pending approvals`
   - `Acceptance rate`
4. Проверьте блок `Farm/site visibility`.
5. Проверьте блок `Linked actions`.
6. Перейдите по ссылкам `Alerts triage`, `Worklists`, `Operational planner`, `Decision / feedback trail`.
7. Вернитесь на `/daily-summary`.
8. Найдите блок `Daily brief preview`.

**Ожидаемый результат:**

- daily summary собирается из canonical DTO bundle;
- ссылки ведут в рабочие разделы;
- видна multi-site сводка;
- preview daily brief присутствует.

**Честная оговорка:** текущий daily brief в React — **preview parity**, не требуйте здесь полнофункционального replacement historical daily brief pipeline.

**Pass / Fail:**

- PASS: экран пригоден как start-of-day surface;
- FAIL: отсутствуют базовые KPI, linked actions или scope summary.

**Reference:** `bash scripts/smoke_t32_05_react_daily_operations.sh`.

---

### WEB-OPS-002 — Alerts triage

**Роли:** Operator/Zootech, Vet, Director, Admin  
**Предусловия:** demo alerts загружены.  
**Шаги:**

1. Откройте `/alerts`.
2. Проверьте заголовок `Alerts`.
3. Проверьте filter input `Filter alerts by farm, entity, type or status…`.
4. Введите `DEMO_COW_2002` и убедитесь, что список сужается.
5. Очистите фильтр.
6. Убедитесь, что на карточках алертов видны severity / reason linkage / linked actions.
7. Перейдите из карточки в linked action, если доступен.
8. Для multi-site окружения проверьте, появляется ли карточка `Multi-site visibility`.

**Ожидаемый результат:** triage работает как read/governance surface, объяснимость показывается из backend evidence.

**Pass / Fail:**

- PASS: фильтр, severity, reason linkage и linked actions работают;
- FAIL: экран превращается в сырую таблицу без triage semantics.

---

### WEB-OPS-003 — Worklists / daily execution

**Роли:** Operator/Zootech, Vet, Admin  
**Шаги:**

1. Откройте `/worklists`.
2. Проверьте заголовок `Worklists`.
3. Проверьте карточки summary: `Visible tasks`, `Open tasks`, `Overdue tasks`.
4. Используйте фильтр по `owner` или `alert`.
5. Убедитесь, что в строках/карточках есть due/overdue semantics и linked hooks.
6. Если присутствуют profile links — откройте object profile в новой вкладке.

**Ожидаемый результат:** worklists пригодны для просмотра и отбора ежедневной очереди.

**Pass / Fail:**

- PASS: есть usable daily execution queue;
- FAIL: нет различия open/overdue/status или ломаются linked object hooks.

---

### WEB-OPS-004 — Planner

**Роли:** Operator/Zootech, Director, Admin  
**Шаги:**

1. Откройте `/planner`.
2. Проверьте заголовок `Planner`.
3. Зафиксируйте summary-карточки планировщика.
4. Проверьте planner items / weekly plans / overdue section.
5. Перейдите по linked actions в reports/assistant/support.

**Ожидаемый результат:** planner summary и weekly plan preview доступны в React.

**Pass / Fail:**

- PASS: planner usable для review;
- FAIL: planner пустой при наличии backend данных или рвёт linked hooks.

---

### WEB-PROFILE-001 — Animal Profile

**Роли:** Operator/Zootech, Vet, Director, Viewer, Admin  
**Предусловия:** использовать `DEMO_COW_1002` или `DEMO_COW_2002`.  
**Шаги:**

1. Откройте `/profiles/animal/DEMO_COW_1002`.
2. Убедитесь, что заголовок = `Animal Profile`.
3. Проверьте карточки metrics: `Open alerts`, `Open worklists`, `Decisions`.
4. Проверьте `Source linkage`.
5. Проверьте `Assistant entry points`.
6. Проверьте `Explainability by object`.
7. Проверьте `Linked actions`:
   - `Explain in assistant`
   - `Decision hook`
   - `Feedback hook`
   - `Open related reports`
8. Проверьте блоки `Linked alerts` и `Linked worklists`.
9. Для Vet повторите на `/profiles/animal/DEMO_COW_2002`.

**Ожидаемый результат:** профиль содержит object context, explainability, source linkage и linked actions.

**Pass / Fail:**

- PASS: профиль usable без Streamlit;
- FAIL: нет source linkage или объяснимость не привязана к backend reasons.

**Reference:** `bash scripts/smoke_t32_06_react_profiles_reports_assistant.sh`.

---

### WEB-PROFILE-002 — Group Profile

**Роли:** Director, Operator/Zootech, Viewer, Admin  
**Предусловия:** использовать `/profiles/group/PEN_N1_LACT` или `/profiles/group/PEN_N2_REPRO`.  
**Шаги:**

1. Откройте `/profiles/group/PEN_N1_LACT`.
2. Убедитесь, что заголовок = `Group Profile`.
3. Повторите шаги 3–8 из сценария WEB-PROFILE-001.

**Ожидаемый результат:** generic profile route корректно отрабатывает для group objectType.

**Pass / Fail:**

- PASS: групповая сущность отображается через тот же reusable profile model;
- FAIL: route не работает или всегда открывает только animal semantics.

---

### WEB-REPORT-001 — Reports catalog

**Роли:** Director, Viewer, Operator/Zootech, Admin  
**Шаги:**

1. Откройте `/reports`.
2. Проверьте заголовок `Report View`.
3. Проверьте filter input.
4. Проверьте summary-карточки `Visible reports`, `Approved`, `Draft / pending`.
5. В таблице выберите первую строку.
6. Нажмите `Open view`.
7. Вернитесь и нажмите `Assistant` у любой строки.

**Ожидаемый результат:** каталог отчётов работает, assistant hook открывается из отчёта.

**Pass / Fail:**

- PASS: отчёты доступны как каталог с version linkage;
- FAIL: каталог не даёт перейти в detail route.

---

### WEB-REPORT-002 — Report detail + governance

**Роли:** Admin, role with report approval permissions; Viewer для read-only части  
**Предусловия:** открыть detail route через каталог.  
**Шаги:**

1. На detail page проверьте карточки `Report version`, `Data version`, `Current status`.
2. Проверьте `Source linkage panel`.
3. Проверьте `Assistant entry points`.
4. Проверьте блок `Report explainability posture`.
5. Проверьте `Linked actions`.
6. Если роль имеет approval permissions — проверьте панель `Report governance`.
7. Введите комментарий.
8. Нажмите `Approve`, затем повторно откройте страницу и проверьте обновившийся статус.
9. Аналогично проверьте `Reject` и `Archive` в non-production test environment.
10. Если роль не имеет approval rights — убедитесь, что кнопки approve/reject/archive недоступны.

**Ожидаемый результат:** governance остаётся server-owned и audit-safe.

**Pass / Fail:**

- PASS: state governance меняется только через server-governed POST и отражается в UI;
- FAIL: governance actions доступны не тем ролям или не меняют статус.

---

### WEB-AI-001 — Assistant entry surface

**Роли:** Director, Operator/Zootech, Vet, Admin  
**Шаги:**

1. Откройте `/assistant`.
2. Убедитесь, что заголовок = `Assistant`.
3. В `data_version` введите `dv_demo_farm_v1`.
4. В `target` введите `alerts`.
5. Нажмите `Resolve target`.
6. Проверьте JSON-result.
7. Откройте `/assistant?target=profile&object_type=animal&object_id=DEMO_COW_1002`.
8. Убедитесь, что отображается `Hook context`.
9. Проверьте, что assistant не рисует собственные причины, а только возвращает backend result.

**Ожидаемый результат:** assistant shell работает как backend-governed resolver surface.

**Pass / Fail:**

- PASS: assistant принимает context и возвращает backend response;
- FAIL: assistant перестаёт работать или invents local logic.

**Честная оговорка:** это thin resolution shell, а не полный чат-копилот с богатыми conversation features.

---

### WEB-DEC-001 — Decision trail

**Роли:** Director, Operator/Zootech, Admin  
**Шаги:**

1. Откройте `/decisions`.
2. Убедитесь, что показывается список решений.
3. Если страница открыта с query params, проверьте блок `Decision hook context`.
4. Зафиксируйте строки по `Action`, `User`, `Created at`.

**Ожидаемый результат:** decision trail остаётся auditable и видимым в новом web UI.

---

### WEB-REPRO-001 — Reproduction surface

**Роли:** Operator/Zootech, Director, Admin  
**Шаги:**

1. Откройте `/reproduction`.
2. Проверьте KPI-карточки:
   - `Open repro worklists`
   - `Overdue repro worklists`
   - `Pending approvals`
3. Проверьте `Scope summary`.
4. Проверьте linked actions в блоке `Linked actions`.
5. Проверьте `Reproduction alerts` и `Reproduction worklists`.
6. Проверьте `Planner preview`.

**Ожидаемый результат:** reproduction review и planner linkage доступны без Streamlit.

**Pass / Fail:**

- PASS: reproduction usable как office workflow surface;
- FAIL: нет repro-specific grouping и planner preview.

---

### WEB-VET-001 — Vet queues

**Роли:** Vet, Admin  
**Шаги:**

1. Откройте `/vet`.
2. Проверьте KPI-карточки:
   - `Queue items`
   - `Overdue items`
   - `High severity alerts`
3. Проверьте linked actions: assistant, decisions, treatments, support.
4. Проверьте `Vet alerts` и `Vet worklists`.

**Ожидаемый результат:** vet triage и follow-up surface usable для office triage.

---

### WEB-TREAT-001 — Treatments / withdrawal

**Роли:** Vet, Admin, Director (read)  
**Шаги:**

1. Откройте `/treatments`.
2. Проверьте KPI-карточки:
   - `Treatment tasks`
   - `Withdrawal watch`
   - `Diagnostics available`
3. Проверьте блок `Governance and evidence`.
4. Сверьте наличие linked actions: vet, assistant, reports, support.
5. Сопоставьте данные с demo `dm_treatments.csv`.

**Ожидаемый результат:** withdrawal/treatment watch виден как governed surface.

---

### WEB-ECON-001 — Economics / what-if

**Роли:** Director, Admin, Accountant/Controller-like role where configured  
**Шаги:**

1. Откройте `/economics`.
2. Проверьте KPI-карточки:
   - `Scenarios`
   - `Reports`
   - `Decision acceptance`
3. Проверьте `ScopeSummary`.
4. Проверьте linked office flows.
5. В таблице scenarios проверьте колонки `Scenario / Status / Report version / Data version`.

**Ожидаемый результат:** economics surface показывает backend scenarios и governance evidence без браузерных формул.

---

### WEB-SUPPORT-001 — Support / governance

**Роли:** Admin, support role, Director (если выданы permissions)  
**Шаги:**

1. Откройте `/support`.
2. Проверьте KPI-карточки:
   - `Open incidents`
   - `Critical incidents`
   - `Support bundles`
3. Проверьте linked actions на observability, readiness, pilot, admin.
4. Если страница открыта с query params, проверьте `Support hook context`.

**Ожидаемый результат:** support surface usable для incident/governance review.

---

### WEB-READINESS-001 — Pilot / Readiness / Observability / Admin

**Роли:** Admin  
**Шаги:**

1. Откройте `/pilot` и проверьте `Pilot packs`, `Latest data version`, `Latest pack`.
2. Откройте `/readiness` и проверьте `Overall status`, `Checks total`, `Warnings / failed`.
3. Откройте `/observability` и проверьте `Requests`, `Jobs`, `Audit events`.
4. Откройте `/admin` и проверьте `Role rows`, `Permission rows`, `Readiness checks`.
5. На `/admin` проверьте `Permission matrix preview`.

**Ожидаемый результат:** office/admin контур доступен как master-system shell.

**Честная оговорка:** React admin page не заменяет полный internal user/password CRUD. Для customer UAT это обычно `N/A`, если не включён отдельный internal admin/support surface.

---

## 7. Что обязательно помечать как N/A, а не как fail

Отмечайте `N/A`, а не `FAIL`, если конкретный поток **осознанно не реализован** в текущем web UI:

- full user CRUD в React admin surface;
- full historical daily brief replacement beyond preview parity;
- расширенный chat-style assistant beyond target-resolution shell;
- любые write-flows, которых нет в текущих React surfaces и которые не подтверждены backend evidence.

---

## 8. Критерии завершения web UAT

Web UAT можно считать завершённым, если:

- все сценарии из раздела 6 пройдены или честно помечены `N/A`;
- нет блокирующих `FAIL` по auth, navigation, profiles, reports, daily operations;
- роль-ориентированная навигация подтверждена;
- governance-sensitive экраны (`reports`, `decisions`, `support`, `readiness`, `admin`) не дают неожиданных прав;
- результаты зафиксированы в `docs/full_uat_checklist.md` или во внешнем QA artefact с теми же scenario IDs.

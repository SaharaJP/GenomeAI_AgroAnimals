# T34 P1-4 «Команда» — реестр рисков и допущений

> Снапшот на 2026-05-15 (после P1-4c-1). Закрытые/устаревшие пункты переходят в `(resolved)`.

Все пункты — то, что **сейчас работает по соглашению** или **может сломаться при росте**. По договорённости с координатором эти долги адресуем в отдельной итерации после P1-4c.

---

## P1-4a-1 — RBAC permissions

- **R1.** Маппинг ролей → permissions хранится в коде (`src/core/security/policy.py`), не в БД. Изменение IAM-матрицы пока требует код-релиза. P1-5 («Админка + IAM-матрица») закрывает это.

## P1-4a-2 — Pydantic-контракт

- **A1.** `pii_visible: bool` пока **не используется на клиенте за пределами /team**; это контрактный флаг под P1-4b. Если другой потребитель будет читать `/personnel`, он должен сам решать, как реагировать на флаг.

## P1-4a-3 — Domain + repository protocol

- **A2.** Не введён абстрактный `PersonnelRepository(Protocol)` — в проекте конвенция «конкретный `*Repo(BaseSqlRepo)` IS the contract». In-memory test-double живёт **только в тестах**. Если Postgres-impl расходится с тестовым double по сигнатуре, тесты молча проходят — нужно следить через code review.
- **R2.** `personnel_id` — серверная строка `prsn_<12-hex>`. Не UUID. Парсеры/потребители не должны полагаться на конкретный формат — это implementation detail.

## P1-4a-4 — Alembic migration personnel_v1

- **A3.** `group_id` — soft-ref на каталог групп, **без DB FK**. Каталог групп как отдельная сущность не существует — каждая строка `personnel_v1.group_id` свободного формата.
- **A4.** `hired_at` хранится как `DATE` в Postgres, но в Pydantic/TS контрактах как ISO-строка. Конверсия — в `core.workflow.personnel.row_to_personnel`. При DB-уровне миграции на другой формат потребуется ручная синхронизация.
- **A5.** PII-колонки (`phone`, `email`, `hired_at`) хранятся **без DB-уровня encryption**. Security-эпик «encrypted PII at rest» — отдельная задача, координатор не запрашивал.
- **R3.** Алфавит индекса `idx_personnel_v1_tenant_name` использует обычный B-tree на TEXT, без collation. Для русской локали сортировка будет байтовая (А → Я, далее а → я). UI компенсирует через `localeCompare(..., 'ru')`, но БД-уровень сортировка отличается.

## P1-4a-5 — Postgres repository impl

- **A6.** Repo возвращает `dict[str, Any]`, не `Personnel` dataclass. Конверсия в типизированную модель происходит в workflow-слое. Удобно сейчас, но если появятся два потребителя одного запроса, оба будут конвертировать дважды.

## P1-4a-6 — Endpoints `/personnel`

- **A7.** Аудит `personnel.list.pii_view` пишется **только если** `pii_visible=True && total>0`. Это компромисс с «каждый просмотр PII = audit_event» — пустые ответы не пишем (нет PII = нет события). Если потребуется логировать каждый GET (для compliance), это надо пересматривать.
- **A8.** Аудит `personnel.create` записывает booleans `has_phone/has_email/has_hired_at`, а НЕ значения. Это сделано, чтобы audit_log сам не стал PII-хранилищем. Trade-off: восстановить ровно «какие значения были при создании» из audit нельзя.
- **R4.** PATCH / DELETE endpoints **не реализованы**. Backlog P1-4 явно требовал только GET+POST. Если UI потребует редактирование карточки сотрудника — это отдельный шаг.
- **R5.** Endpoint требует `personnel.read`/`personnel.manage` — но **не проверяет**, что target tenant_id совпадает с caller'ом. Сейчас `tenant_id = user.get('tenant_id', 'default')` — корректно, но если в будущем admin сможет переключать tenant'ы в URL, это место надо охранить.

## P1-4a-7 — Photo upload via MinIO ⏸ **DEFERRED**

- **R6.** MinIO в локальном dev-контуре **не поднят**. `photo_ref` принимается endpoint'ом как opaque string, UI отдаёт placeholder-аватары (инициалы). Реальная заливка вернётся когда MinIO будет живым (вероятно в составе P1-6 «Контроль интеграций»). Документировано в `T34-product-backlog-2026-05.md:170-172` и в коммите `cb0b50b`.

## P1-4b-1 — /team route + skeleton + navigation

- **A9.** URL state — `?view=by-group | by-name`, **НЕ** `?tab=...` как у `/vet`. Сделано осознанно, чтобы оставить `?tab=` под возможный под-табинг внутри карточки сотрудника. Если UX-эксперт скажет иначе, переименование — мелкий патч.

## P1-4b-2 — Personnel list + PII rendering

- **A10.** `photo_ref` рендерится напрямую через `<img src={person.photo_ref}>` без Next.js Image optimization. Когда MinIO заработает и `photo_ref` будет S3 URL'ом, потребуется либо CORS proxy, либо переход на `next/image` с конфигом remote patterns.
- **A11.** Список рендерится **без виртуализации**. Для >200 сотрудников будет тормоз; для ферм этого порядка не дойдём в P1-4, но в P2 (масштабирование) — потребуется виртуализация.
- **A12.** Сортировка — `localeCompare(..., 'ru')` в браузере. Для очень больших списков (тысячи строк) сортировка-в-браузере неуместна — нужна серверная (`ORDER BY full_name COLLATE "ru_RU"`).

## P1-4b-3a — `personnel.user_id` FK

- **A13.** `user_id` — **soft-FK без DB constraint**. `personnel_v1.user_id` может ссылаться на несуществующий `auth_users.id`. Целостность гарантируется только на уровне приложения (UI выбирает из реального списка). Если будут массовые скрипты — нужны проверки.
- **R7.** Маппинг personnel → user сейчас **не имеет UI** — только через прямой POST с готовым `user_id`. Бэкенд-готовность есть, UI-обвязка (выбор пользователя в админке) — отдельный шаг, не запланирован формально.

## P1-4b-3b — Personnel detail drawer

- **R8.** «Личные задачи» рендерятся **все одним массивом** (admin → 417 строк). Виртуализации/пагинации нет. Для типичного пользователя (единицы задач) ОК, но для admin/director может тормозить.
- **A14.** `/worklists` фильтр `owner_user_id` теперь публичный query param — он не задокументирован в TS-контракте (используется raw URL-construction). Если появятся другие callers, можно вынести в `Worklists?` тип.
- **R9.** При закрытии drawer'a задачи **перезагружаются** при следующем открытии — нет кэша. На сетях с задержкой это даёт мигание UI. Для P2 — добавить SWR/React Query.

## P1-4c-1 — POST /worklists

- **R10. ⚠ ВАЖНО.** **Импеданс-mismatch:** `Personnel.group_id` — free-form строка (из POST /personnel), а `Tasks.assignee_team` валидируется против каталога `configs/workflow_v2/teams.yaml` (5 ключей: team-health, team-repro, team-data, team-qc, team-econ). Если UI «Поставить задачу» передаст `personnel.group_id` напрямую в `assignee_team`, будет **500** (ValueError из `_validate_team`). Это **блокер для P1-4c-2** — нужно решение:
  1. Унифицировать: `personnel.group_id` ограничить значениями из teams.yaml (dropdown в POST /personnel).
  2. Маппер: free-form `group_id` → ближайший team-key, fallback `null`.
  3. Расширить teams.yaml: добавить «команды команд» (Ветеринары/Зоотехники/…) поверх существующих 5.
  4. Развязать поля: в карточке сотрудника group_id отображается, но в задаче assignee_team выбирается отдельно из team catalog.
- **R11.** `priority` валидируется 1..5 в endpoint, но `core.workflow.tasks.create_task` сам тоже валидирует/нормализует. При расхождении границ — endpoint вернёт 400, но если миновать endpoint (например через workflow напрямую), границы могут не совпасть.
- **A15.** `task_type='manual'` хардкоден в endpoint. Если позже понадобится дифференцировать manual-задачи по подтипу, нужно завести enum в контракте.
- **A16.** Audit `tasks.create.manual` записывает `has_due_at: bool`, а не само значение. Та же логика, что в personnel.create — не превращать audit в зеркало данных. Trade-off: для отладки приходится смотреть и audit, и tasks_v1 одновременно.

---

## Сводка по приоритетам (что точно надо адресовать)

| ID | Уровень | Что | Зачем |
|---|---|---|---|
| **R10** | 🔥 высокий | `personnel.group_id` ↔ `tasks.assignee_team` mismatch | блокирует P1-4c-2 UX |
| R6 | средний | MinIO не поднят, photo upload отложен | UX-наличие фото |
| R4 | средний | Нет PATCH/DELETE на `/personnel` | редактирование карточки |
| R7 | средний | Нет UI для personnel↔user mapping | админка |
| A5 | низкий | PII без DB encryption | compliance |
| R8/R9 | низкий | Нет пагинации/кэша в drawer | производительность |
| A11/A12 | низкий | Нет виртуализации/сортировки на сервере | масштаб |
| R3 | низкий | DB-сортировка без локали | UX в админ-инструментах |

---

## Что НЕ риск (вынесено в обычные follow-up'ы)

- P1-4d (FAB модалка) — следующая по плану задача, не "риск".
- TS-контракт `worklists?owner_user_id` — простое расширение, без долга.
- Component-unit тесты для Personnel UI — полагаемся на Playwright runtime; добавить в P2 если нужно.

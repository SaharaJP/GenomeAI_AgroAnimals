# T34 P1-5 «Администрирование + IAM-матрица» — реестр рисков и допущений

> Снапшот на 2026-05-15 (после слайса 3 — backend complete). Слайсы 4 (UI editing + 2-click confirm) и 5 (docs)
> по договорённости остановлены здесь, чтобы оставить контур в безопасном read-only состоянии до отдельного
> согласования edit-UX. Backend полностью функционален и пишет audit на каждое изменение.

---

## P1-5 slice 1 — /admin tile canon

- **A1.** Плитки на `/admin` сейчас зашиты массивом `TILES` в `web_app/components/extended/admin-command-center.tsx`. Это намеренно — каждая плитка имеет статичный icon (lucide-react) и человекочитаемое описание. Если плиток станет больше 5, имеет смысл вынести в data-конфиг.
- **A2.** На `/admin` сохранены три верхних метрик-карточки (Ролей / Permission-строк / Readiness-проверок), но они теперь могут показывать `—` при недоступности backend (`fetchExtendedBundle` ошибка не блокирует рендер плиток). Это сознательный UX-trade-off: даже на упавшем backend admin должен иметь точки входа в наблюдаемость/поддержку.
- **R1.** `/admin/iam` плитка ведёт на новый маршрут — на стадии слайса 1 ещё не было готовой страницы. Закрылось в слайсе 2.

## P1-5 slice 2 — /admin/iam read-only

- **A3.** Endpoint `/api/admin/permission-matrix` отдаёт **высокоуровневую** view-структуру: `{version, actions[], rows?}`. Каждое action — логическая группа (5 элементов: upload, run, export, approve, config) с массивом permissions внутри. Это значит что НЕ каждая permission видна в матрице — только те, что объявлены в `configs/security/permission_matrix_v1.yaml`. Permissions, добавленные только в `policy.py` (например, `personnel.manage`), в UI-матрице не появляются.
- **R2.** Чекбоксы в read-only режиме — `disabled` HTML-атрибут, что предотвращает изменения, но визуально может вводить в заблуждение (пользователь не понимает что edit недоступен). В слайсе 4 нужно либо включить интерактив, либо добавить tooltip «Только просмотр».
- **A4.** Запросы к `/api/admin/permission-matrix` идут через web_app proxy (`/api/backend/api/admin/permission-matrix`). Маршрут защищён `personnel.manage` (PERM_USERS_MANAGE) на backend. Если у роли нет этого права, GET вернёт 403, UI покажет error-text.

## P1-5 hotfix — list_roles / get_permissions_for_role

- **A5.** `roles` и `role_permissions` таблицы — **опциональные**. Их физическое отсутствие на контуре не блокирует RBAC (есть YAML/policy fallback). Hotfix wraps `conn.execute` в try/except и принудительно делает `conn.rollback()`, чтобы избежать `InFailedSqlTransaction` cascade.
- **A6.** Fallback использует константы `_DEFAULT_ROLES` и `DEFAULT_ROLE_PERMISSIONS` из policy.py. Это значит что добавление новой роли через `roles` таблицу — production-only feature; в dev/test ролевой каталог фиксирован.
- **R3.** Если кто-то добавит `roles` таблицу с другим набором ролей чем константы, runtime будет читать DB, но fallback на DEFAULT может вернуться при ошибках. То есть `roles` table — must-be-complete: либо все 8 ролей, либо ничего.

## P1-5 slice 3 — IAM DB-overrides backend

### Архитектура
- **A7.** Effective permissions = `YAML_baseline.union(grants).difference(revokes)`. Это set-операция; одна (role, permission) пара имеет ровно один эффект через PK ограничение в `role_permissions_overrides_v1`.
- **A8.** PATCH endpoint принимает `effect: 'grant' | 'revoke' | 'clear'`. `clear` удаляет override-строку → роль возвращается к YAML default'у.
- **A9.** Endpoint валидирует `permission` против `rbac.ALL_PERMISSIONS` (constants in policy.py, не YAML). YAML может содержать подмножество — добавление новой permission в policy.py делает её сразу editable через PATCH, даже если YAML её не упоминает.
- **A10.** Role catalog для валидации = `list_roles(conn)`. С hotfix'ом он всегда возвращает 8 default-ролей минимум. PATCH с произвольной "Imposter" ролью → 400.

### Известные риски
- **R4. ⚠ важно.** **Process-cache invalidation.** Существующие auth-сессии кэшируют permissions в `user['permissions']` при создании сессии (`web_cabinet/auth.py:332`). PATCH-овые overrides применяются только при **следующем login или refresh**. Это значит:
  - Если оператор только что revoke'нул `alerts.view` у себя — он ещё пять минут (или до logout) сможет ходить по `/alerts`.
  - Если оператор granted permission себе — она появится после re-login.
  - **Mitigation:** в слайсе 4 показать в confirm-dialog: «Изменение вступит в силу после следующего входа пользователей с этой ролью».
  - **P2:** ввести force-logout всех сессий с этой ролью (или session-bus invalidation через Redis).
- **R5. ⚠ важно.** **Race conditions.** Два admin'a параллельно PATCH'ат одну и ту же (role, permission) пару → последний `INSERT … ON CONFLICT DO UPDATE` выигрывает. Audit запишет оба события. Допустимо для P1; в P2 можно добавить optimistic locking через ETag / If-Match header.
- **R6. ✅ RESOLVED (P1-5/P1-6 R-debt 2026-05-15).** Backend hard-guard в `PATCH /api/admin/permission-matrix`: любой запрос с `{role: 'Admin', permission: 'admin.manage', effect: 'revoke'}` отклоняется 400 `iam.lock_out_protected`. Защищает от случайного и намеренного lock-out. UI confirm-dialog «опасных» операций остаётся как фолоу-ап в slice 4.
- **R7. ✅ RESOLVED (P1-5/P1-6 R-debt 2026-05-15).** Endpoint теперь читает `get_override(conn, role, permission)` перед mutation; для grant→revoke перехода audit_log пишет `before_json={...effect: 'grant'}`, что позволяет проследить предыдущий state по одной строке audit.
- **A11.** Endpoint возвращает `effective_permissions_count` для убедительности — UI может показывать «X permissions effective» после change, давая ощущение что изменение применилось.

### Что не сделано (слайс 4)
- Интерактивные чекбоксы на `/admin/iam` — сейчас disabled.
- 2-click confirm dialog с явным текстом «Изменение применится после следующего входа пользователей с этой ролью».
- Сравнение «текущее значение vs YAML default» — UI пока не показывает, что cell переопределена.
- Force-logout пользователей с роли после PATCH (можно отложить в P2).
- Hard guard «нельзя revoke admin.manage у роли Admin».

### Public interface footprint
- `GET /api/admin/permission-matrix` — был; gate `personnel.manage` (PERM_USERS_MANAGE).
- `PATCH /api/admin/permission-matrix` — **новый**; gate `admin.manage`. Зарегистрирован в `docs/public_interfaces.json`.

---

## Сводка по приоритетам

| ID | Уровень | Что | Зачем |
|---|---|---|---|
| R4 | 🔥 высокий | Кэш сессий — overrides не применяются в текущей сессии | UX/security clarity |
| R5 | средний | Race на параллельный PATCH | data consistency |
| ~~R6~~ | ✅ resolved | ~~revoke admin.manage = lock-out~~ | backend hard-guard в P1-5/P1-6 R-debt 2026-05-15 |
| ~~R7~~ | ✅ resolved | ~~before_json неинформативен на повторных PATCH~~ | get_override-before-upsert в P1-5/P1-6 R-debt 2026-05-15 |
| R2 | низкий | Disabled чекбоксы без объяснения | UX |
| A3 | низкий | YAML actions ≠ all permissions | matrix coverage |

---

## Что НЕ риск

- Pytest baseline: 15 failed / 17 passed в security scope — это снимок ДО моих правок; ни одного нового падения.
- Audit table `audit_log` — соглашение по именованию см. `MEMORY.md` (reference-audit-log-table).
- Миграция `20260515_19_role_permissions_overrides`: применена локально, downgrade присутствует, никакие prod-применённые миграции не редактировались.

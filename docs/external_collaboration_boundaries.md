# T28-04 — External consultant / partner collaboration boundaries

## Что добавлено

Система получила централизованный слой внешнего сотрудничества без ad hoc permission logic по страницам:

- роли `Consultant` и `Partner` в общей RBAC-модели;
- collaboration boundary profile на уровне пользователя;
- bounded farm/site access для external specialists;
- отдельные collaboration entries: `comment`, `recommendation`, `approval_request`;
- internal review flow для разрешённых внутренних ролей;
- полный audit trail для создания и review collaboration entries.

## Модель boundary

Для пользователя теперь можно хранить:

- `collaboration_mode` (`internal`, `external_consultant`, `external_partner`)
- `external_org`
- `allowed_farm_ids_json`
- `allowed_site_ids_json`
- `collaboration_flags_json`

External user работает в deny-by-default режиме:

- если scope не задан, доступ к данным не даётся;
- если объект не принадлежит разрешённому `farm/site`, доступ блокируется;
- скрытых cross-farm leaks быть не должно.

## Что разрешено external roles

По умолчанию external roles получают bounded read access и collaboration actions:

- просмотр bounded worklists / benchmark views / drilldown surfaces;
- комментарии;
- рекомендации;
- запросы на approval.

External roles не получают полноценный internal governance control.

## Approval / review model

External specialist может создать `approval_request`, но review выполняется только ролью, у которой policy разрешает `collaboration.approvals.review`.

Review не меняет исходный audit trail и не удаляет note; вместо этого note переводится в статус `accepted / rejected / resolved`.

## UI surfaces

На текущем шаге collaboration boundaries встроены в:

- `Admin → Users / Security` — настройка external boundary profile;
- `Daily Worklists By Role` — bounded collaboration entries и review;
- `Animal Profile` / `Group Profile` — scope guard against cross-farm access.

## Explainability / governance

Каждый collaboration entry хранит:

- кто создал;
- роль;
- collaboration mode;
- external organisation;
- объект и scope;
- статус review;
- linked metadata.

Это сохраняет governance и делает совместную работу безопасной для multi-farm / enterprise эксплуатации.

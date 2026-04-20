# Operational fast query mode

`Fast query mode` — это bounded и explainable слой для power users, который ускоряет сбор сложных operational списков и report targets без raw query execution и без превращения UI в developer console.

## Что поддержано

- compact query/filter input в одной строке;
- безопасный parser с ограничением длины, числа токенов и явным запретом unsafe markers;
- target routing в три surface-типа:
  - `list` → `Universal list builder`
  - `report` → `Operational report builder`
  - `profile` → `Animal Profile` / `Group Profile`
- query history через existing audit log (`fast_query.run`);
- favorites и pinned queries через existing favorites store;
- saved views integration через `saved_views_v1`;
- explain plan: target, filters, sort, columns, limit, warnings.

## Practical syntax

Примеры:

- `animals status:active breed:Holstein sort:latest_event_date:desc`
- `events family:health severity:high after:2026-03-01`
- `report:health animal:A1002 severity:high cols:event_date,animal_id,event_type`
- `open:animal:A1002`

Поддерживаемые bounded tokens:

- targets: `animals`, `groups`, `events`, `report:<alias>`, `open:animal:<id>`, `open:group:<id>`
- filters: `farm:`, `site:`, `pen:`, `animal:`, `status:`, `sex:`, `breed:`, `family:`, `type:`, `severity:`, `after:`, `before:`
- rendering/options: `sort:<field>[:asc|desc]`, `cols:<c1,c2,...>`, `limit:<n>`, `scc:<threshold>`

## Safety / boundedness

- raw SQL / raw DSL execution отсутствуют;
- `;`, `--`, `/*`, `*/`, backticks не принимаются;
- длина запроса и число токенов ограничены;
- неизвестные structured tokens не исполняются, а попадают в warnings;
- любой результат сводится к существующим safe surfaces, где уже действуют RBAC и role-aware field visibility.

## History / favorites / pinned queries

- `history` собирается из `audit_log` по action `fast_query.run`;
- `favorites` хранятся в `favorites_v1` с `object_type=fast_query`;
- `pinned queries` хранятся в `favorites_v1` с `object_type=pinned_fast_query`;
- metadata содержит page-state, поэтому query можно открыть повторно через global favorites page.

## Ограничения

- Это не legacy CLI clone и не full BI DSL.
- Arithmetic expressions, joins, custom formulas и raw aggregations в syntax не поддерживаются.
- Для сложных визуальных/аналитических сценариев пользователь должен перейти в `Universal list builder` или `Operational report builder`.

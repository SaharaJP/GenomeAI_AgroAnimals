# Multi-site operational model

## Что добавлено

- Введён единый enterprise-ready слой `farm -> site -> group -> pen` в `core.operational.multi_site`.
- Сохранена backward compatibility: если отдельного `group_id/group_name` нет, система честно делает fallback `group = pen`, не ломая single-farm и существующие `pen`-ориентированные flows.
- Runtime items (`worklists`, planner items, alerts-derived items) теперь могут быть обогащены текущим operational context: `farm_id/site_id/group_id/pen_id`, physical location, organizational location и lineage path.
- Добавлены explainable consolidated aggregates по farm/site/group: это не скрытая метрика, а прозрачный count уже видимых items по scope.
- На daily worklists и operational planner добавлены site-aware filters и consolidated enterprise view.
- На Animal Profile и Group Profile добаван показ физического и организационного текущего расположения объекта.

## Модель иерархии

- `farm` — верхний организационный и отчётный уровень.
- `site` — площадка внутри farm; используется как access/filter boundary и уровень consolidated reporting.
- `group` — operational grouping для исполнения работы. Может совпадать с pen, если отдельная сущность group не экспортируется источником.
- `pen` — физическое текущее местоположение.

## Explainability aggregated metrics

Consolidated tables намеренно ограничены простыми explainable агрегатами:

- `items_total`
- `high_priority`
- `overdue`
- `today`
- `animals_n`
- `source_kinds`
- `object_types`
- `explainability`

Каждая строка aggregate читается как: «сколько именно отфильтрованных operational items попало в этот scope и из каких источников они сложились».

## Access boundaries

Поддерживаются soft enterprise boundaries через `allowed_farm_ids / allowed_site_ids`.

Если такие ограничения переданы в user/session context, UI режет видимые items до разрешённых farm/site ещё до consolidated summary. Это не заменяет полноценный policy-engine, но даёт bounded enterprise-safe scope layer уже сейчас.

## Почему это не ломает single-farm UX

- Фильтры остаются опциональными.
- Single-farm пользователь по-прежнему может работать без заполнения farm/site/group/pen.
- Если multi-site контекст отсутствует, страницы показывают только доступные уровни и не выдумывают недостающие hierarchy links.
- Existing `farm/site/pen` abstractions reused, а не заменены новой incompatible сущностью.

## Ограничения итерации

- Полноценный tenant/site policy engine и серверные hard boundaries по RBAC в этой итерации не вводятся.
- Если runtime object не имеет animal/group linkage и source facts не содержат scope, aggregate fallback идёт только на явно доступный уровень.
- Исторический context движений по группе/pen по-прежнему опирается на current/asof assignment snapshot, а не на full historical topology graph.

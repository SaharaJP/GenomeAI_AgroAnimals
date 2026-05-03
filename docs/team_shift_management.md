# Team / shift management

## Что сделано в T28-02

- Введён lightweight ownership layer поверх existing worklists/tasks: `team + shift + user`, без превращения системы в HR/scheduling.
- Source-of-truth ownership semantics сохранены: `owner_user_id` и `assignee_team` не заменены, а дополнены traceable shift/handover metadata.
- Реализован `handover_worklist_use_case`: handover between shifts/team/user записывается в `attachments[kind=handover]`, дублируется в `why.ownership` и всегда пишет audit `worklist.handover`.
- Daily Worklists и Operational Planner теперь умеют фильтровать по `team` и `shift`, показывать queue balance и handover monitoring.
- Queue balance intentionally explainable: агрегаты строятся только по текущему visible queue и показывают `items_total / overdue / today / load_units / team_unowned`, без скрытого KPI engine.
- Single-farm и обычный role-based execution не ломаются: если shift metadata нет, queue остаётся usable через `assignee_team` и/или `owner_user_id`.

## Ограничения

- Это не full HR/scheduling system: нет графиков смен, табеля, отпусков, присутствия и capacity planning по людям.
- Shift — это operational label queue ownership (`day/evening/night/unassigned`), а не календарный кадровый контур.
- Handover не создаёт отдельный workflow object: traceability обеспечивается через audit + attachments + `why.ownership`.
- Role-aware boundaries сделаны lightweight: Admin/Director могут handover между любыми командами, executor roles — только в рамках своего team scope.

## Acceptance mapping

- Ownership by team/shift/user: есть.
- Handover between shifts: есть, traceable.
- Queues by team: есть в daily/planner filters и queue balance widgets.
- Overdue monitoring: есть в queue balance и handover monitor.
- Workload / queue balance: есть, explainable, derived from visible items only.

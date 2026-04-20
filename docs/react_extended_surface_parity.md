# T32-07 — React extended surface parity

Цель шага: довести новый `web_app/` до состояния, где офисный/управленческий пользователь может работать в React не только с daily operations, profiles и reports, но и с оставшимися взрослыми контурами:

- reproduction
- vet queues
- treatments / withdrawal
- economics / what-if
- admin / observability / support / pilot / readiness

## Что перенесено в React

Новые React surfaces:

- `/reproduction`
- `/vet`
- `/treatments`
- `/economics`
- `/support`
- `/pilot`
- `/readiness`
- `/observability`
- `/admin`

## Backend evidence и допустимые допущения

Этот шаг **не** вводит новую бизнес-логику в frontend.

React использует только подтверждённые backend evidence surfaces:

- canonical `/api/app/v1/*` для alerts/worklists/planner/economics/support/pilot/readiness/decision-intelligence;
- server-side BFF proxy routes для legacy, но серверно подтверждённых admin/observability surfaces:
  - `/api/admin/permission-matrix`
  - `/api/observability`

Группировка reproduction/vet/treatments во frontend делается только по backend-полям (`worklist_type`, `domain`, `task_type`, `alert_type`, `severity`, `linkage`) и рассматривается как **view composition**, а не как новая предметная логика.

## Governance / auditability / diagnostics

Сохраняются:

- governance
- auditability
- enterprise filters / tenant-farm-site scope
- diagnostics
- support / pilot / readiness flows
- export/report/admin hooks

React не ослабляет admin/support/release surfaces и не делает React-only shortcuts без backend evidence.

## Parity posture

На этом шаге `web_app` закрывает **полный офисный/управленческий пользовательский контур** системы.

Это означает:

- ежедневная работа доступна в React;
- profiles / reports / assistant / explainability доступны в React;
- reproduction / vet / treatments / economics / admin surfaces доступны в React.

При этом Streamlit всё ещё остаётся legacy transitional UI до formal cutover evidence по всему продукту. Но для офисной/управленческой работы новый web frontend уже выступает как master system shell.

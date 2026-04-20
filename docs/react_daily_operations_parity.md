# React daily operations parity (T32-05)

## Что зафиксировано

На этом шаге в `web_app/` перенесён **ежедневный operational contour** в режиме **read parity**:

- home / daily summary → `/daily-summary`
- alerts → `/alerts`
- worklists → `/worklists`
- operational planner → `/planner`
- daily brief preview → встроен в `/daily-summary` и `/planner`

Все экраны используют только canonical backend boundary `/api/app/v1/*` и не содержат новой бизнес-логики.

## Что считается parity evidence на этом шаге

Parity измеряется не визуальным сходством со Streamlit, а проверяемыми признаками:

1. У legacy-surface есть явный React route.
2. Route использует canonical backend contract, а не внутренние Python-модули.
3. Есть linked actions / explainability entry points / decision hooks.
4. Single-farm и multi-site scope видимы в React shell.
5. Есть checked-in parity map: `configs/parity/react_daily_operations_parity_v1.json`.
6. Есть tests/smoke, которые детектируют пропажу этих surfaces.

## Граница этого шага

Это **не** formal cutover completed и **не** разрешение удалять Streamlit.

На T32-05 зафиксирована только ежедневная read parity для ключевых operational surfaces. До formal parity evidence и отдельного cutover gate:

- legacy Streamlit layer removed in T32-12; React daily operations is the active product UI;
- legacy Streamlit layer removed in T32-12;
- write-actions parity и final replacement evidence должны идти отдельными шагами.

## Legacy → React mapping

| Legacy surface | React route | Backend contract | parity level |
|---|---|---|---|
| Home / home_v3 | `/daily-summary` | alerts + worklists + planner + reports + decision-intelligence | implemented_read_parity |
| Alert Center v2 | `/alerts` | `/api/app/v1/alerts` | implemented_read_parity |
| Worklist v1 / Daily Worklists By Role | `/worklists` | `/api/app/v1/worklists` | implemented_read_parity |
| Operational Planner / Weekly Plans | `/planner` | `/api/app/v1/planner` | implemented_read_parity |
| AI Daily Brief | `/daily-summary` preview | derived canonical bundle | preview_only |

## Что теперь доступно в React

- daily summary / start-of-day shell
- alerts triage cards
- worklists daily queue
- planner summary + weekly plans + overdue backlog
- daily brief preview
- linked actions to decisions / assistant / support hooks
- explainability entry points from canonical DTOs
- farm/site visibility for single-farm and multi-site contexts

## Проверка

- `npm run smoke` в `web_app/`
- `pytest -q tests/test_t32_05_react_daily_operations_parity.py`
- проверка checked-in parity map against real files/routes

# apps/web

Будущий web frontend кабинетного уровня.

На текущем шаге каталог создан как явная точка назначения для нового UI, чтобы не продолжать развивать продуктовый UI в Streamlit.

## Scope

- role-based кабинеты
- dashboards / drill-down
- workflows / approvals
- reports / admin / integrations
- React/Next.js app shell

## Правило

Новый кабинетный UI-код пишется только здесь.

Веб-клиент не содержит бизнес-логики и не рассчитывает доменные решения локально.


## T32-04 foundation

Первый runnable foundation создан в `web_app/`.
`apps/web/` остаётся target-ownership каталогом верхнего уровня, а `web_app/` — фактической реализацией frontend shell на данном этапе.

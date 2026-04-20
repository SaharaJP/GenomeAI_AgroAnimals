# Operational SLA / rollout gates

T28-05 добавляет лёгкий enterprise-ready слой operational gates поверх уже существующих CI/smoke механизмов.

## Что проверяется

Профиль `enterprise_ci` запускает 5 стабильных gate-категорий:

1. `compile_daily_pages` — синтаксическая проверка daily-use и enterprise pages без браузерной автоматизации.
2. `role_scenarios` — role smoke / role UX visibility / acceptance reuse из Streamlit final gates.
3. `mobile_views` — лёгкие script-level smoke для mobile shell/worklists + compile мобильных страниц.
4. `worklists_profiles_reports` — script-level smoke для action flow, profiles UX и reports UX.
5. `rollout_diagnostics` — наличие policy/script/docs/admin diagnostics surface + ссылки на последние CI diagnostics artifacts.

## Почему это не flaky-heavy UI automation

- нет Selenium/Playwright/browser-grid;
- используются compile checks, existing role smoke и короткие deterministic python-smoke scripts;
- gate переиспользует уже сгенерированные `post-removal regression report` и related artifacts, если они есть.

## Локальный запуск

```bash
pip install -e .
bash scripts/run_operational_rollout_gate.sh
```

Или точечно:

```bash
PYTHONPATH=src:. python scripts/smoke_t28_05_operational_rollout_gates.py   --project-root .   --artifacts artifacts   --profile enterprise_ci   --report-root artifacts/_ci/operational_rollout_gates   --workdir _tmp/ci_operational_rollout
```

## Артефакты

- `artifacts/_ci/operational_rollout_gate.log`
- `artifacts/_ci/operational_rollout_gates/operational_rollout_gates_report.json`
- `artifacts/_ci/operational_rollout_gates/operational_rollout_gates_report.md`

## Admin diagnostics

`Admin → Наблюдаемость и диагностика` теперь умеет показывать `operational_rollout_gates` рядом с performance/warning/restore diagnostics.

## Интерпретация

Gate считается готовым к enterprise rollout, когда:

- role scenarios не деградировали;
- mobile/worklists/profiles/reports smoke зелёные;
- ключевые daily-use страницы компилируются;
- rollout diagnostics surface присутствует и выдаёт диагностируемый JSON/MD отчёт.

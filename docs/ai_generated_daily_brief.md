# T29-05 — AI-generated daily brief under governance

## Что добавлено

- Это именно **role-specific daily brief**, а не общий freeform summary.
- Добавлен `daily brief generator` как facts-only слой поверх Home / reports / workflow surfaces.
- Brief **не** подменяет Home pages отдельным AI shell: Home остаётся стартовым экраном, а brief встроен как governed preview + full brief view.
- Daily brief строится в `src/core/ai_daily_brief.py` и использует только факты системы, versions и существующие linked actions.
- Для каждого пункта brief показываются:
  - linked facts,
  - linked actions,
  - expected effect.
- Brief всегда reproducible and version-linked: `brief_version`, `data_version`, `report_version` и прочие source versions входят в payload.
- fallback without LLM обязателен и является default mode (`facts_template`).

## Где это видно

- `Home v3` показывает compact preview daily brief.
- `pages/69_AI_Daily_Brief.py` даёт полный role-specific brief view.
- `Report View` даёт переход в daily brief, если нужен start-of-day/governance read path от report facts к actions.

## Governance / approval / archive / share

- Approval flow не дублируется отдельным ad hoc engine: при наличии linked report применяется existing approvals center.
- Archive / approval review notes фиксируются append-only в `Decision Log`.
- Share flow идёт через `saved_views` + copy-ready share context.
- Все действия audit-safe.

## Ограничения

- Нет freeform summary без source facts.
- Нет отдельного hidden LLM mode для brief.
- Brief не является отдельным report approval object; governance reuse-ит existing flows where applicable.

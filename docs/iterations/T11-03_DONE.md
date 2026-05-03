# T11-03 DONE — Unit economics + ROI attribution (animal/group)

## Итог по задачам

1) **Unit economics** (`unit_economics`): витрины по животным и группам (pen/site/farm) с компонентами доходов/расходов и маржой.
2) **ROI attribution** (`roi_attribution`): эффект от решений/закрытых задач по марже (до/после и diff-in-diff при наличии контроля), с привязкой к `data_version/run_id`.
3) **Связка с decision_log/tasks**: действия подтягиваются из `decisions/decision_log.csv` и (опционально) из `web.db` (`decision_log_v2`, `tasks_v1`).
4) **Качество и дисклеймеры**: флаги качества в `roi_actions.csv`, сводка `roi_quality.csv`, дисклеймеры в `manifest.json` и UI.
5) **Web-cabinet**: профили животного/группы показывают вклад (unit economics), ROI панель показывает attribution и drill-down (детали по действию — при включённых outputs).

## Acceptance criteria (покрытие)

- В профиле животного виден вклад и компоненты (доход/корма/прочие/вет/репро/выбытие) + ссылки на `unit_econ_run/economics_run`.
- ROI панель показывает эффект по периодам (roi_summary), по действиям (roi_actions) и связку с решениями/задачами (source/source_id).
- Есть дисклеймеры по причинности и качеству данных (limitations + quality flags + roi_quality).

## Артефакты

`artifacts/<data_version>/unit_economics/<unit_econ_run>/...`
`artifacts/<data_version>/roi/<roi_run>/...`
и копии в `artifacts/<data_version>/runs/<run_id>/...`.
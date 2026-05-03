# Operational report builder

`T24-02` добавляет быстрый слой operational reports поверх уже существующих core/use-cases, `saved views`, `favorites` и export-пайплайна.

## Что умеет

- быстрые readable reports для daily users, а не только analysts;
- report surfaces: `animals_overview`, `groups_overview`, `events_recent`, `repro_attention`, `health_attention`, `milk_quality_watchlist`;
- filters, sort, column selection, exports `CSV/XLSX`;
- linked actions from report rows: переход в `Animal Profile`, `Group Profile`, repro/vet surfaces;
- saved report templates через existing `saved views` integration (`page_key=operational_report_builder`);
- favorites / pinned operational reports через existing favorites store.

## Что не делаем

- не переписываем текущий report generation backend;
- не строим full BI DSL;
- не считаем heavy logic в Streamlit.

## Прозрачность формул / assumptions

Каждый report показывает таблицу `Formulas / assumptions`.

Базовые прозрачные формулы:

- `utilization_pct = headcount / capacity_head * 100`
- `active_treatments = count(dm_treatments where end_date is null or end_date >= asof_date)`
- `milk_quality_flag = high_scc if latest_scc_cells_ml >= threshold; treatment_withdrawal if active_treatments > 0; else ok`
- `health_attention` использует `event_family in [health, treatment]`
- `repro_attention` использует `event_family == reproduction`

## Saved templates / favorites / pinned reports

- reusable template = saved view state для `operational_report_builder`
- pinned report = favorite с `object_type=operational_report`
- favorites открываются через страницу `Saved Views And Favorites`

## Acceptance intent

Пользователь может быстро получить нужный operational report, выгрузить его и перейти от строки отчёта к действию без внешнего BI или ручных CSV-скриптов.

# T10-04 — step3: Saved views for Director Summary + Favorites for Dashboard Reports

## Что добавлено

1) **Director Summary**: сохранение/восстановление представлений (saved views) включая:
   - `data_version`, `kpi_run_id`, `asof_date`
   - путь к конфигу целей/порогов (`targets_rel`)
   - **набор виджетов** (список KPI плиток)

2) **Dashboard Reports**: возможность добавить/убрать выбранный `report_version` в избранное (`object_type=dashboard_report`), а также открыть элемент избранного из страницы "Saved views + Favorites".

3) **UI**: страница `17_Saved_Views_And_Favorites` теперь поддерживает `director_summary` в списке сохранённых представлений.

4) **Tests**: добавлены проверки матрицы прав ролей по T10-04 (templates view/write).

## Принципы

- UI (Streamlit) **не считает KPI**: только показывает артефакты и дергает offline-core.
- Все важные пользовательские действия (create/apply saved view, favorite add/remove) пишутся в audit log через `audit_action`.

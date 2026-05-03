# T10-04 — Saved Views + Report Templates + Favorites (DONE)

## Что реализовано

### 1) Saved Views (фильтры/представления)

- Хранение представлений в `web.db`: `saved_views_v1`.
- Поддержаны страницы: `kpi_drilldown`, `alert_center`, `director_summary`.
- Сохраняемые ключи включают: `data_version`, `run_id` (если применимо), `asof_date`, выбранный `pen_id` для KPI drill-down, список `tile_ids` для Director Summary.
- Scope: `user` (только автор) и `shared` (все пользователи tenant). `shared` ограничен правом `configs.manage`.
- Аудит: create/apply/delete пишутся в audit log (`saved_view.*`).

### 2) Report Templates + «конструктор отчёта»

- CRUD шаблонов в `web.db`: `report_templates_v1`.
- Поля шаблона: `sections`, `metrics`, `options_json`, scope `user/shared`.
- Генерация отчёта по кнопке в **offline-core**: `src/genomeai/template_reports.py`.
- Артефакты создаются в `artifacts/<data_version>/reports_regular/<report_version>/exports/`:
  - `report_director.{md,html,pdf}`
  - `report_ops.{md,html,pdf}`
- «Конструктор отчёта»: на странице запуска можно **переопределить** sections/metrics и задать focus (`group|animal|alert`) без изменения сохранённого шаблона.
- Аудит: create/update/delete и `pipeline.report_template.run` пишутся в audit log.

### 3) Избранное (favorites)

- Таблица `favorites_v1`: поддержаны типы `report`, `dashboard_report`, `alert`, `group/pen`, `animal/cow`.
- UI для избранного + переходы (deep-links) вынесены на страницу `17_Saved_Views_And_Favorites`.
- Фильтрация избранного по роли/правам: неизвестные типы скрываются, доступ проверяется через permissions.
- Аудит: `favorite.add` / `favorite.remove`.

## Как проверить вручную

1) Запустить web-cabinet:
   - `make web` или `streamlit run streamlit_app/app.py` (как в проекте).
2) KPI Drilldown:
   - выбрать `pen` → сохранить view → перезагрузить → применить view → `pen` восстановился.
3) Report Templates:
   - создать template → сформировать PDF → открыть Report View (страница 16) → скачать PDF.
4) Favorites:
   - добавить отчёт/группу/животное в избранное → открыть через страницу 17 → убедиться, что без нужных прав объект скрыт.

## Автотесты

- `pytest -q tests/test_t10_04_*`

## Ссылки на шаги итерации

- `docs/iterations/T10-04_step2_template_report_generation.md`
- `docs/iterations/T10-04_step3_director_saved_views_and_dashboard_favorites.md`
- `docs/iterations/T10-04_step4_report_builder_focus_and_role_filtered_favorites.md`
- `docs/iterations/T10-04_step5_saved_views_state_and_pen_id.md`

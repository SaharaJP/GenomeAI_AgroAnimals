# T10-04 (step4): Report builder overrides + focus filtering + role-filtered favorites

## Что добавлено

### 1) «Конструктор отчёта» при запуске шаблона

В `Report Templates` добавлены переопределения **только для текущего запуска** (шаблон в БД не меняется):
- выбор `sections` (разделы);
- выбор `metrics` (KPI из `configs/kpi/kpi_v2.yaml`, fallback — вручную);
- `focus_type/focus_id` для сужения отчёта на сущность (group/animal) или на конкретный alert.

### 2) Фокус в offline-core (без вычислений в веб)

`focus_type/focus_id` трактуются как **фильтр фактов**, пришедших из web-cabinet:
- `group/pen` и `animal/cow`: фильтрация по `object_type/object_id` с поддержкой алиасов;
- `alert`: фильтрация alert по `alert_id`, а tasks/decisions по `related_alert`.

KPI/top-листы:
- если фокус — `group/pen`, то топ животных строится с `pen_id=<focus_id>`, топ групп фильтруется по `pen_id`;
- если фокус — `animal/cow`, то топ животных фильтруется по `animal_id`, и (если возможно) извлекается `pen_id` из строки для фильтрации топа групп.

### 3) Роли и избранное

Добавлена явная роль/пермишн логика для генерации отчётов по шаблонам:
- новый пермишн: `report_templates.generate`.

Фильтрация «избранного» вынесена в Streamlit-free модуль и покрыта тестами:
- скрываем неизвестные типы;
- `alert` требует `alerts.view`, `report` требует `export.download`, `group/animal` требует `drilldown.view`.

## Тесты

Добавлены тесты:
- роль/пермишн для `report_templates.generate`;
- корректность маппинга пермишнов для favorites;
- фильтрация фактов по `focus_type/focus_id` в `run_template_report`.

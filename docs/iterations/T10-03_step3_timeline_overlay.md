# T10-03 Step3 — Drill-down 3.0: таймлайн-компонент + auto asof + audit

## Что добавлено

1) **Auto asof_date**:
   - Director Summary / KPI Drilldown: default asof берётся из `kpi_long.asof_date` (если присутствует в артефактах KPI-run).
   - Alert Center: `asof` для профилей животного/группы берётся из метаданных алерта (`why.asof_date`/`attachments`/`created_at`).

2) **Timeline component v1** (`streamlit_app/components/timeline_v1.py`):
   - Рендер фактов (offline-core `build_animal_timeline`) + overlay из web.db: `tasks_v1` и `decision_log_v2`.
   - Фильтрация по категориям и ограничение `max_rows`.

3) **Аудит переходов**:
   - KPI Drilldown → Group Profile
   - Group Profile → Animal Profile

4) UI defaults вынесены в `configs/ui/drilldown_v3.yaml` (без "жёстких" констант в коде).

## Пояснения по границам слоёв

- Offline-core отвечает за сбор событий (repro/health/sensors/milk) и отдаёт таблицу фактов.
- Web-cabinet отвечает за CRUD задач/решений и audit-log.
- Timeline component — это только отображение и объединение уже подготовленных объектов.

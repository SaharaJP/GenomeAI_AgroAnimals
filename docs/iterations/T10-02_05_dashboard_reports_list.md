# T10-02 — Dashboard Reports list (web-cabinet)

Цель: дать пользователю кабинета список сохранённых снимков дашбордов ("save as report")
и быстрый доступ к скачиванию экспортов (PNG/PDF/XLSX/CSV) без пересчёта.

## Что добавлено
- Offline-core: функции чтения manifest и списка файлов экспорта (`genomeai.dashboard_reports`).
- Web-cabinet: страница Streamlit **"📸 Dashboard Reports"** (`pages/13_Dashboard_Reports.py`).
- Audit log: клики на скачивание пишутся как `export.download` (object_type=`dashboard_report`).

## Где лежат данные
- manifest: `artifacts/<data_version>/metadata/dashboard_report_manifest.json`
- exports: `artifacts/<data_version>/reports/<report_version>/dashboard/<dashboard_kind>/exports/`

## Проверка
1) Создайте dashboard snapshot и сохраните как report (кнопка на Director Summary или CLI).
2) Откройте страницу "Dashboard Reports" и выберите `data_version`.
3) Убедитесь, что:
   - список отображается и сортируется по `created_at_utc` (новые сверху)
   - доступны кнопки скачивания PNG/PDF/XLSX/CSV
   - в `web.db` есть audit события `export.download`

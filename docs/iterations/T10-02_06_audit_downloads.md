# T10-02 (Step 6): Audit log для скачиваний snapshot на Director Summary

## Цель
Закрыть требование "все критичные действия логируются" для действий пользователя на дашборде директора:

- скачивание XLSX/PDF/PNG/CSV артефактов последнего snapshot;
- фиксация `data_version` и `run_id` snapshot'а.

## Что сделано
В `streamlit_app/pages/1_Director_Summary.py` добавлен thin-wrapper `_download_button_with_audit(...)`,
который:

1) читает файл из artifacts;
2) показывает `st.download_button`;
3) при клике пишет запись в audit log:

- `action=export.download`
- `object_type=dashboard_snapshot`
- `object_id=<abs path to file>`
- `data_version=<dv>`
- `run_id=<dashboard run_id>`
- `after={file, dashboard_kind}`

UI не считает бизнес-логику и не генерирует артефакты: только показывает уже созданные offline-core export файлы.

## Как проверить
1) Сгенерировать snapshot (кнопка "Generate XLSX/PDF/PNG snapshot" на Director Summary).
2) Нажать любую кнопку скачивания (XLSX/PDF/PNG/CSV).
3) Проверить, что в `web_cabinet/storage/web.db` появилась запись в `audit_log`:

```sql
SELECT created_at_utc, action, object_type, data_version, run_id, object_id
FROM audit_log
WHERE action='export.download'
ORDER BY id DESC
LIMIT 20;
```

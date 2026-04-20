# T11-04 Step3 — What‑If 2.0: PDF отчёт по сценарию

## Цель

Добавить воспроизводимый PDF-отчёт по сценарию what‑if:

1) Отчёт строится **строго из артефактов economics** (без LLM).
2) В отчёте фиксируются предпосылки (параметры сценария) и прозрачные формулы.
3) Отчёты индексируются в `web.db` и доступны для скачивания с учётом RBAC.

## Что реализовано

### Offline-core

Файл: `src/genomeai/whatif_report.py`

- Генерация PDF `whatif_report.pdf` (reportlab).
- Метаданные `report_meta.json` + `manifest.json` + `checksums.json`.
- Отчёт использует `summary_farm.csv` из `economics_run` и читает колонки
  `*_baseline`/`*_scenario` для BASE vs SCENARIO.

Артефакты:

```
artifacts/<data_version>/whatif_reports/<report_version>/
  whatif_report.pdf
  report_meta.json
  manifest.json
  checksums.json
```

### Web-cabinet

- Новая таблица `whatif_reports_v1` (индексация отчётов).
- Модуль доступа: `web_cabinet/whatif_reports_v1.py`.
- API:
  - `GET /api/whatif_reports_v1?scenario_id=...` (просмотр списка)
  - `GET /api/whatif_reports_v1/{report_version}` (карточка отчёта)
  - `POST /api/whatif_scenarios_v1/{scenario_id}/report_pdf` (генерация)

RBAC:

- `whatif.report.view`
- `whatif.report.generate`

Все действия пишутся в `audit_log`.

### Streamlit (mini-web)

Страница `streamlit_app/pages/9_Economics_WhatIf.py`:

- Блок "Отчёт по сценарию (PDF, T11-04)":
  - список отчётов для выбранного сценария
  - кнопка генерации
  - скачивание последнего PDF

## Проверка

### Тесты

```
pytest -q
```

### Ручная проверка (Streamlit)

1) Запустить кабинет:

```
streamlit run streamlit_app/app.py
```

2) Зайти под `zootech/zootech`.
3) Открыть "Экономика / What-if".
4) Сохранить сценарий (или выбрать существующий), посчитать economics.
5) Нажать "Сгенерировать PDF отчёт".
6) Скачать PDF и проверить, что внутри:
   - контекст (data_version, period, cfg)
   - параметры сценария
   - формулы
   - таблица BASE vs SCENARIO + дельты

# Reporting (A5)

## Цель

Сформировать отчёт для пользователя на основе результатов:

- QC: `artifacts/<data_version>/qc/<qc_run>/qc_summary.json`
- ML: `artifacts/<data_version>/models/<model_version>/model_card.json`
- Scoring: `artifacts/<data_version>/scoring/<scoring_run>/scoring_summary.json` и экспортов

## Fact pack — единый источник правды

Команда `genomeai report` собирает единый `fact_pack.json` и сохраняет его в:

`artifacts/<data_version>/reports/<report_version>/fact_pack.json`

Этот JSON является **единственным** источником чисел/таблиц для:

- LLM-режима (если включён)
- fallback-режима (шаблонный отчёт)

## Режимы генерации

### 1) LLM mode

`--mode llm`

LLM получает **только** содержимое `fact_pack.json` и инструкцию:

- не добавлять новые числа/проценты/метрики
- если факта нет — писать `NA`

Дополнительный guardrail: любая числовая токенизация в тексте, которой нет в `fact_pack.json`, заменяется на `n/a`.

Если LLM недоступен (нет ключа/ошибка), команда автоматически переключается в fallback.

### 2) Fallback mode

`--mode fallback` (по умолчанию)

Всегда доступен. Отчёт собирается из фиксированного шаблона, заполненного значениями из `fact_pack.json`.

## Форматы

- `report.docx` — обязателен
- `report.pdf` — best-effort (можно отключить `--no-pdf`)

## Версионирование

`report_version` создаётся как `report_<timestamp>_<suffix>`.

Связка версий фиксируется в:

- `artifacts/<data_version>/reports/<report_version>/report_summary.json`
- `artifacts/<data_version>/metadata/report_manifest.json`

## Гейтинг (правило)

Если QC статус `ERROR`, последующие этапы (включая ML) **должны** считаться заблокированными.

На A5 отчёт может быть сформирован и при `ERROR`, но должен явно показывать QC статус.

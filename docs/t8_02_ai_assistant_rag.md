# T8-02: AI‑ассистент “только по данным системы” (RAG + guardrails)

Документирует источники знаний, RAG и guardrails для ассистента.

## Источники знаний

Ассистент строит контекст **только** из артефактов системы:

- KPI‑витрины и алерты (fact-pack из T8-01): `artifacts/<data_version>/...`
- Decision Log (legacy CSV) и Decision Log v2 (SQLite `web.db`)
- Последние регулярные отчёты (MD/HTML/PDF) из `artifacts/<data_version>/reports_regular/<report_version>/...`

## Fact-pack формат

Внутренний `fact_pack` дополняется блоком:

```json
{
  "assistant_knowledge": {
    "schema": "genomeai.fact_pack.assistant.v1",
    "decision_log_legacy": {"available": true, "sources": {...}, "top": [...]},
    "decision_log_v2": {"available": true, "sources": {...}, "top": [...]},
    "regular_reports_latest": {"available": true, "report_version": "...", "sources": {...}}
  }
}
```

## Цитирование

Каждый ответ включает блок `Источники/версии`:

- `label` — логический ключ блока/таблицы
- `source` — путь к файлу или `web.db:table`
- `data_version`, `model_version`, `report_version`

## Guardrails

Жёсткие правила:

1) Запрещены диагнозы/лечение — только риск/факты и действия (осмотр/проба/перепроверка данных).
2) Запрещены ответы вне данных системы.
3) Нельзя придумывать цифры: числа в ответе должны присутствовать в retrieved‑context, иначе заменяются на `NA`.
4) Любая рекомендация — decision-support и может быть подтверждена пользователем с записью в Decision Log.

## Логирование

Каждый запрос/ответ записывается в `assistant_log_v1` (SQLite `web.db`) как append-only JSON.

## Тесты

Набор тест-кейсов (15+) определён в `tests/test_t8_02_ai_assistant_rag.py`.

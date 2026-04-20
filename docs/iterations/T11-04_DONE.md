# T11-04 — DONE (What‑If 2.0)

## Закрытые цели
1) **Сохранение сценариев what-if** (draft/approved/archived) + RBAC на create/update/approve/clone/archive.
2) **Сравнение 2–3 сценариев** с BASE (Streamlit UI + API `/api/whatif_compare_v1`).
3) **PDF отчёт по сценарию** (fact-based, без LLM) + индексирование (`whatif_reports_v1`).
4) **Audit** всех критичных действий.

## Быстрая проверка acceptance
```bash
pytest -q tests/web/test_t11_04_e2e_flow.py
```

## Основные артефакты
- Scenarios: `web.db` таблица `whatif_scenarios_v1`
- Reports: `web.db` таблица `whatif_reports_v1`
- PDF: `artifacts/<data_version>/whatif_reports/<report_version>/whatif_report.pdf`


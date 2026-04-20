# T10-04 Step2 — Генерация отчёта по шаблону (saved views + report templates)

Что добавлено:

1) Offline-core генератор отчёта по шаблону: `genomeai.template_reports.run_template_report`.
   Он формирует артефакты отчёта (MD/HTML/PDF) строго из фактов + данных артефактов.
2) Streamlit UI (страница **18_Report_Templates**) получил кнопку **«Сформировать PDF»**.
   UI только собирает факты из `web.db` (alerts/tasks/decisions) и вызывает offline-core для рендера.
   Для совместимости с существующим просмотрщиком отчётов шаблонный отчёт сохраняется как regular report.

Пути артефактов:

* `artifacts/<data_version>/reports_regular/<report_version>/exports/report_director.*`
* `artifacts/<data_version>/reports_regular/<report_version>/exports/report_ops.*`

Проверка (локально):

```bash
pytest -q tests/test_t10_04_personalization_crud.py tests/test_t10_04_template_report_generation.py

# запуск UI
python -m streamlit run streamlit_app/Home.py
```

В UI:

1) Откройте «Report Templates».
2) Создайте/выберите шаблон.
3) Внизу заполните `data_version` и нажмите «Сформировать PDF».
4) Нажмите «Открыть в Report View».

Аудит:

* `pipeline.report_template.run` — на генерацию отчёта.

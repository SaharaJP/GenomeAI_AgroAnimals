# Report-to-action bridge

T24-05 делает `Report View` точкой входа в исполнение, а не только read-only просмотром артефакта.

## Что добавлено

- bounded bridge-слой поверх существующего `Report View`;
- context bridge от `row/section` отчёта к `profile / alert / task / worklist / decision`;
- извлечение actionable rows из `fact_pack` where possible;
- section-level bridge из `TOC` + report versions/facts;
- создание `decision` и `worklist` только через existing use-cases;
- audit linkage для действий, созданных из отчёта.

## Источник контекста

Bridge использует только уже существующие артефакты:

- `report_summary.json`
- `fact_pack.json`
- markdown TOC из report export

Backend генерации отчётов, артефакты и versioning не меняются.

## Что считается bridge context

### Row-level context

Строится из object-level rows в `fact_pack`, в первую очередь из:

- `top_lists.*`
- `productivity_explainability.animal_explainability`

Для row-level context сохраняются:

- `context_id`
- `context_kind=row`
- `section`
- `source_path`
- `object_type/object_id`
- `linked_alert_id / linked_task_id / linked_worklist_id / linked_decision_id` when present
- `source_facts`
- `linked_objects`

### Section-level context

Строится из TOC markdown headings.

Для section-level context сохраняются:

- `context_kind=section`
- `section`
- `anchor`
- версии отчёта/пайплайна как linked objects
- section-specific facts where possible (`qc`, `ml metrics`, `scoring counts`)

## Доступные действия из отчёта

Для выбранного bridge context пользователь может:

- открыть `Animal Profile` / `Group Profile`
- открыть существующий `Alert`
- открыть существующий `Task / Worklist`
- открыть существующее `Decision`
- создать `Decision from report`
- создать `Worklist from report`

## Audit / linkage

При создании action из отчёта сохраняются:

- `data_version`
- `qc_run`
- `model_version`
- `scoring_run`
- `report_version`
- `report_context_id`
- `context_kind`
- `section`
- `source_path`
- `source_facts`
- `linked_objects`

Дополнительно пишутся audit события:

- `report.bridge.decision.create`
- `report.bridge.worklist.create`

## Ограничения

- Bridge не подменяет `Report View workflow engine` и не меняет existing report artifacts.
- Row-level bridge работает только там, где `fact_pack` действительно содержит object-level actionable rows.
- Если object-level context отсутствует, остаётся section-level bridge на уровне самого отчёта.
- Это не новый task/decision DSL: все действия идут только через существующие use-cases.

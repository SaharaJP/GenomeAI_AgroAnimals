# T32-06 — React profiles / reports / assistant / explainability parity

Цель шага: сделать профили, отчёты, embedded assistant entry points и object-level explainability доступными в новом `web_app/` без зависимости от Streamlit.

## Что перенесено в React

- `Animal Profile` и `Group Profile` через общий route `/profiles/[objectType]/[objectId]`
- `Report View` через каталог `/reports` и detail route `/reports/[dataVersion]/[reportVersion]`
- embedded assistant entry points
- reusable explainability component model
- decision-intelligence widgets
- report governance hooks через server-side BFF route

## Boundary rules

1. Frontend не invent factors/explanations.
2. Explainability показывает только то, что пришло из backend DTO / audit / version linkage.
3. Assistant остаётся в fact-pack only режиме.
4. source linkage обязательно видно пользователю: `data_version`, `model_version`, `report_version` где применимо.
5. Linked actions остаются server-governed: React только открывает hooks и проксирует governance action.

## Reusable component model

- `FactPackGuardrailNote`
- `SourceLinkagePanel`
- `ObjectExplainabilityPanel`
- `AssistantEntryPoints`
- `DecisionIntelligenceWidgets`
- `ProfileSurface`
- `ReportCatalogSurface`
- `ReportViewSurface`
- `ReportGovernancePanel`

## Profiles parity

Profile surface должна давать:

- summary counters
- linked alerts
- linked worklists
- decision trail hooks
- assistant hooks
- object explainability by backend-provided reasons only

## Reports parity

Report surface должна давать:

- report catalog
- report detail by `data_version + report_version`
- source/version linkage
- governance status
- approve/reject/archive hooks where permissions allow
- assistant hooks

## Guardrails

- Нельзя придумывать факторы по объекту или отчёту на фронтенде.
- Нельзя размножать explanation logic по разным страницам; используется общий reusable component model.
- Нельзя ослаблять assistant guardrails или обходить fact-pack only режим.
- Streamlit не нужен для работы с профилями/отчётами/assistant/explainability в новом web UI, но formal cutover legacy UI всё ещё отдельный шаг.

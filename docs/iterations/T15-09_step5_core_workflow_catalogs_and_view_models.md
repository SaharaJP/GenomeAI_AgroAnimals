# T15-09 Step 5 — core workflow catalogs and listing view-models

## Что вынесено в core
- `core.workflow.catalogs`: stage/team catalogs, default/open stage, UI-ready options.
- `core.workflow.view_models`: canonical workflow listing payload for mini-web page.

## Что осталось в адаптерах
- Playbook recommendation decoration for `/workflow` rows remains in `web_cabinet.app` because it depends on web-side playbook wiring.
- Audit writing remains in UI/API adapters.

## Совместимость
- `/api/workflow_v2/stages` и `/api/workflow_v2/teams` сохраняют старый payload shape.
- `workflow.html` по-прежнему фильтрует по stage, но options теперь приходят из core.
- Streamlit Worklist использует тот же stage/team catalog path из core.

# T15-09 / step 1 — core.workflow + legacy shims

## Что сделано
- Создан новый пакет `src/core/workflow`.
- В него перенесены модули:
  - `alerts.py`
  - `tasks.py`
  - `decisions.py`
  - `entities.py`
- Legacy `web_cabinet.*` модули сведены к shim/re-export слою.
- Публичные функции и сигнатуры сохранены.
- Config-driven SLA / auto-tasking / overdue / decision linkage продолжают работать через core.

## Почему это безопасно
- Перенос сделан почти verbatim, без изменения API surface.
- Existing UI/API imports остаются рабочими.
- E2E/web tests на alerts/tasks/decision log проходят без изменения сценариев.

## Что ещё не сделано
- First-party adapters (`web_cabinet.app`, Streamlit pages) ещё не переведены на прямой импорт `core.workflow.*`; пока они используют legacy paths, которые уже делегируют в core.
- Единый high-level Action Center builder/use-case ещё не выделен отдельно.
- Стандартизация reason codes / status labels / audit payload builders ещё не выделена в отдельные core helpers.

## Проверка
- pytest по workflow/domain/web compatibility
- `bash scripts/smoke_offline.sh`
- `python -m genomeai verify_refactor ...`

# T15-09 — step 3

## Что сделано
- Добавлен `core.workflow.policies` для стандартизации SLA/due derivation, overdue flag и advisory reason-codes.
- Добавлен `core.workflow.lifecycle` с едиными use-cases для acknowledge/resolve alert, take/update/close task и append decision.
- `web_cabinet.app` переключён на lifecycle use-cases для workflow actions.
- Streamlit Action Center и Worklist переключены на lifecycle use-cases вместо прямой orchestration-логики.
- Сохранена backward compatibility: low-level functions и free-text reasons продолжают работать.

## Почему это безопасно
- Хранилища, схемы таблиц и публичные route/entrypoints не менялись.
- Audit по-прежнему формируется в adapter-слое, но after/before теперь берутся из единых core use-cases.
- Причины закрытия/resolve стандартизированы через config, но не стали обязательным жёстким enum.

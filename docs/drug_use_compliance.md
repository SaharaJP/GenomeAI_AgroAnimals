
# Drug use / compliance / approval trail

## Что добавлено
- Append-only trail `drug_use_compliance_v1` для применения препаратов.
- Явные действия: `prescribed`, `approved`, `executed`, `rejected`.
- Явные поля approval trail: кто назначил / кто подтвердил / кто выполнил / когда.
- Linkage на `treatment_course`, `protocol_reference`, `linked_object`, `alert`, `health_event`, `worklist`.
- Compliance-ready exports по текущему состоянию курса и по полной append-only истории.

## Принципы
- Approval state не хранится в комментариях.
- Все изменения append-only; update/delete trail rows запрещены.
- Источник состояния лечения остаётся в `treatment_journal_v1`; compliance trail — отдельный append-only слой поверх него.
- Legacy `dm_treatments` остаются read-only и не редактируются через этот экран.

## Основные use-cases
- `record_drug_prescription_use_case(...)`
- `approve_drug_use_use_case(...)`
- `execute_drug_use_use_case(...)`
- `build_drug_use_compliance_snapshot(...)`

## Что видно в UI
- course-level compliance view
- append-only history
- history by animal / group / farm
- export CSV

## Ограничения
- Это не clinical diagnosis engine.
- Это не заменяет специализированный pharmacy / dispensary контур.
- Для write-path поддерживаются runtime treatment courses; legacy курсы остаются read-only.

# Streamlit transitional policy

## Статус

`removed_streamlit_legacy/` считается transitional/deprecated surface для периода миграции.

## Для чего Streamlit ещё допускается

- поддержка уже существующих сценариев;
- smoke/parity verification;
- временный fallback во внедрениях до formal cutover;
- support/admin demo для уже существующего контура.

## Что запрещено

- писать новый целевой продуктовый UI в Streamlit;
- добавлять в Streamlit новую бизнес-логику;
- делать Streamlit источником правды по workflow/RBAC/audit;
- проектировать новые продажи как Streamlit-first решение.

## Как помечать legacy-пути

Любой legacy Streamlit flow, заменяемый web/mobile/API путём, должен быть помечен как:

- `transitional`;
- `deprecated for new development`;
- `subject to cutover gate`.

## Условия удаления

Удаление Streamlit возможно только при наличии:

- parity matrix legacy -> target;
- green smoke/e2e regression;
- runbook cutover/rollback;
- подтверждения, что операционные роли не теряют критичные ежедневные сценарии.

# Web cutover / coexistence / rollback runbook (T32-11A)

## Что фиксирует этот шаг

T32-11A добавляет **воспроизводимый go/no-go процесс** перевода customer/pilot environments со Streamlit-контура на новый web frontend.

Runbook **не** удаляет Streamlit и **не** подменяет parity "по ощущениям". Он связывает:

- formal parity gate из `T32-11`;
- coexistence phase;
- customer/pilot verification;
- rollback criteria;
- operator-facing signoff;
- incident/support discipline.

## Статусы go/no-go

Поддерживаются только три статуса:

- `no_go`
- `go_pending_operator_signoff`
- `go`

### Как трактуются статусы

- `no_go` — хотя бы один обязательный блок не готов: parity gate, coexistence assets, rollback readiness или verification kit.
- `go_pending_operator_signoff` — техническая готовность и rollback plan есть, но нет полного signoff от операторской/внедренческой стороны.
- `go` — parity gate пройден, coexistence/rollback/verification готовы и присутствует operator signoff.

## Обязательные предпосылки

Cutover допускается только если одновременно соблюдены условия:

1. T32-11 gate показывает минимум `ready_for_cutover`.
2. Для customer/pilot environment задана **coexistence phase**.
3. Есть rollback plan и rollback criteria.
4. Есть verification checklist/script set.
5. Есть operator-facing signoff.

Без этого новый web frontend может быть **готов к cutover**, но customer migration всё равно остаётся в статусе `no_go` или `go_pending_operator_signoff`.

## Фазы runbook

### Phase 0 — Pre-cutover preparation

Проверяется:

- parity gate status;
- environment profile (`pilot`, `customer_stage`, `customer_prod`);
- routing/ingress readiness;
- support contact and incident owner;
- backup/restore readiness;
- rollback target URLs.

### Phase 1 — Coexistence

Оба контура существуют одновременно:

- Streamlit остаётся enabled;
- новый web frontend включён для bounded cohort;
- migration verification и smoke проходят по согласованным сценариям;
- операторы работают по feature-by-feature readiness matrix.

### Phase 2 — Bounded cutover

Для конкретного customer/pilot environment:

- primary office users переводятся на новый web frontend;
- Streamlit остаётся как rollback contour;
- incidents и operator feedback собираются по фиксированной форме.

### Phase 3 — Stabilization

Проверяется:

- нет unresolved P1/P0 incident'ов;
- support и operator signoff завершены;
- rollback больше не требуется для текущего env;
- environment может считаться `go`.

## Coexistence rules

Во время coexistence обязательно:

- **не** отключать Streamlit globally;
- переводить пользователей/фермы по environment-решению, а не "одним рубильником";
- вести feature-by-feature readiness matrix;
- фиксировать incident owner и rollback decision owner.

## Rollback rules

Rollback обязателен, если возникает хотя бы одно условие:

- blocked office workflow по одному из required scenarios;
- loss of linked actions / report governance / admin access;
- failed operator signoff;
- incident severity >= `high` без workaround;
- migration verification drift, делающий данные/действия недоверенными.

Rollback делается **не как manual panic**, а через явные шаги из checked-in runbook/configs.

## Verification assets

Runbook использует:

- T32-11 parity gate/evidence;
- T26 migration verification toolkit;
- T26 parallel run mode;
- T26 migration playbook and cutover;
- T32-05/06/07 parity surfaces and smoke.

## Текущий честный статус репозитория

На текущем шаге runbook показывает:

- `overall_go_no_go = go_pending_operator_signoff`
- Cutover completed in T32-12; rollback target is previous web release, not Streamlit.

Это означает:

1. технический cutover process уже воспроизводим;
2. coexistence и rollback формально описаны и проверяемы;
3. Streamlit всё ещё нельзя выключать без operator signoff и отдельного approval-пакета.


## Machine-readable runbook assets

- `configs/cutover/web_cutover_runbook_v1.json`
- `configs/cutover/web_cutover_verification_checklist_v1.json`
- `configs/cutover/web_cutover_rollback_criteria_v1.json`
- `configs/cutover/web_cutover_feature_readiness_matrix_v1.json`
- `configs/cutover/web_cutover_customer_env_template_v1.json`
- `configs/cutover/web_cutover_operator_signoff_template_v1.json`

## Команды

Регенерация runbook evidence:

```bash
python scripts/validate_t32_11a_web_cutover_runbook.py --write
python scripts/validate_t32_11a_web_cutover_runbook.py --assert-current
```

Smoke:

```bash
bash scripts/smoke_t32_11a_web_cutover_runbook.sh
```

Pytest:

```bash
pytest -q tests/test_t32_11a_web_cutover_runbook.py
```

## Ограничения

- Runbook не исполняет deployment cutover автоматически.
- Runbook не подменяет customer change-management.
- Runbook не даёт права выключить Streamlit без T32-11 approval и operator signoff.
- Runbook измеряет readiness/evidence и rollback discipline, а не визуальное сходство экранов.

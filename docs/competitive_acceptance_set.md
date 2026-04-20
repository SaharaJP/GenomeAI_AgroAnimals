# Competitive acceptance set (T30-01)

T30-01 фиксирует **формальный acceptance set для сценариев замены legacy herd-management systems**.

Это не маркетинговый список фич и не purely manual UAT.
Acceptance set строится как regression-ready набор из:

- deterministic automated checks;
- versioned report artifacts;
- explicit pass/fail criteria;
- bounded manual signoff checklist по сценариям.

## Какие сценарии покрываются

Профиль `legacy_replacement_ci` включает шесть сценариев:

1. `daily_operations`
2. `reproduction`
3. `vet`
4. `reports_worklists`
5. `mobile`
6. `migration`

Для каждого сценария сохраняются:

- automated checks;
- manual checks;
- итоговый статус:
  - `not_ready`
  - `ready_for_manual_signoff`
  - `product_ready`

## Что считается automated evidence

Acceptance runner умеет использовать два типа regression evidence:

1. уже созданные CI artifacts:
   - `post-removal regression report`
   - `operational_rollout_gates_report.json`
2. прямой deterministic запуск bounded subsets:
   - `pytest -q <targeted tests>`
   - `python <stable smoke script>`

Это позволяет не строить тяжёлую browser automation и не превращать acceptance set в flaky gate.

## Manual signoff

Manual signoff **не обязателен для CI-pass**, но обязателен для статуса `product_ready`.

По умолчанию runner читает файл:

- `artifacts/_qa/competitive_acceptance/manual_signoff.json`

Минимальный формат:

```json
{
  "scenarios": {
    "daily_operations": {
      "signed_off": true,
      "signoff_by": "qa_lead",
      "signoff_at": "2026-04-05T12:00:00Z",
      "notes": "field UAT complete"
    }
  }
}
```

Если automated checks зелёные, но signoff отсутствует, сценарий получает статус `ready_for_manual_signoff`.

## Локальный запуск

```bash
bash scripts/run_competitive_acceptance_gate.sh
```

Либо напрямую:

```bash
PYTHONPATH=src:. python scripts/smoke_t30_01_competitive_acceptance_set.py \
  --project-root . \
  --artifacts artifacts \
  --profile legacy_replacement_ci \
  --report-root artifacts/_ci/competitive_acceptance
```

Можно запускать только отдельные сценарии:

```bash
PYTHONPATH=src:. python scripts/smoke_t30_01_competitive_acceptance_set.py \
  --scenario daily_operations \
  --scenario migration
```

## Артефакты

Runner пишет:

- `artifacts/_ci/competitive_acceptance/competitive_acceptance_report.json`
- `artifacts/_ci/competitive_acceptance/competitive_acceptance_report.md`
- `artifacts/_ci/competitive_acceptance_gate.log`

## Что считается pass/fail

### Scenario pass

Scenario проходит automated part, если одновременно выполняется всё ниже:

- все configured artifact checks = ok;
- все targeted pytest bundles = ok;
- все stable smoke scripts = ok;
- все required docs/files присутствуют;
- duration укладывается в scenario budget.

### Overall CI pass

Gate считается успешным, если весь acceptance set достигает статуса:

- `ready_for_competitive_uat=true`

Это означает:

- ни один сценарий не находится в `not_ready`;
- команда может формально перейти к bounded manual signoff.

### Product-ready

Статус `product_ready` выставляется только если:

- automated checks зелёные;
- есть explicit manual signoff evidence.

## Почему это полезно для replacement readiness

Acceptance set связывает в одном формальном наборе:

- daily operations,
- reproduction,
- vet,
- reports/worklists,
- mobile/cowside,
- migration/cutover evidence.

Это позволяет команде честно сказать:

- какие сценарии уже готовы к конкурентной замене legacy HMS;
- какие ещё проходят только automated readiness;
- какие пока blocked и почему.

# Pilot framework and reference deployments

T31-01 добавляет **runnable pilot tracking contour** вместо презентации/таблицы.

## Что входит

- Формальный framework для **2–5 пилотов** с явными статусами, expected outcomes, success criteria и role model.
- Файловые tracking objects: `data/pilots/pilot_framework_v1/pilot_records_v1.json`.
- Reusable core summary builder: `src/core/pilot_framework.py`.
- In-product page: `pages/74_Pilot_Framework_And_Reference_Deployments.py`.
- Smoke runner: `scripts/smoke_t31_01_pilot_framework.py`.

## Что именно отслеживается

Для каждого пилота:
- статус пилота;
- scope по farms/sites/roles;
- expected outcomes;
- success criteria;
- linkage к `data_version`, `qc_run`, `model_version`, `scoring_run`, `report_version`, `decision_log`;
- support cases;
- incidents;
- manual evidence для reference claim;
- explicit `referenceable=true/false`.

## Governance rule

**Reference deployment не считается подтверждённым автоматически.**

Даже если pilot record в статусе `completed`, reference claim блокируется, пока не приложены явные evidence-поля (`customer_signoff`, acceptance/support evidence).

## Как запускать

```bash
PYTHONPATH=src:. python scripts/smoke_t31_01_pilot_framework.py \
  --project-root . \
  --report-root artifacts/_ci/pilot_framework_v1
```

Ожидаемые артефакты:
- `artifacts/_ci/pilot_framework_v1/pilot_framework_report.json`
- `artifacts/_ci/pilot_framework_v1/pilot_framework_report.md`

## Ограничение

Seed records в репозитории — **starter/sample records** для runnable validation. Это не доказательство реальных field deployments и не основание заявлять full-scale rollout readiness.

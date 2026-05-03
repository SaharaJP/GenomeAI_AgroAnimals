# Performance / NFR gates

T17-05 добавляет coarse-grained performance budgets для синтетических и CI-сценариев без вмешательства в бизнес-логику.

## Что измеряется

Профиль `ci` из `configs/ops/performance_gates_v1.yaml` включает 4 gate:

1. `startup`
   - cold-ish import `web_cabinet.app`
   - выполнение `_startup()` на временных `artifacts/web_storage`
2. `pipeline_smoke`
   - offline synthetic pipeline: ingest → qc → train → score → report → decision log → pack
3. `web_smoke`
   - `python -m web_cabinet.smoke` с шагами RBAC / ingest / qc / train / score / report / decisions / pack
4. `verify_refactor`
   - `standard` и `qc_issues` сценарии по одному, с отдельным timing на каждый scenario

## Политика budget'ов

- Budget'ы intentionally coarse и с запасом, чтобы ловить грубые регрессии, а не микрофлуктуации среды.
- Gate считается проваленным, если:
  - общий `duration_sec` превышает `budget_sec`, либо
  - отдельный step/scenario превышает свой step budget.
- Эти проверки не являются microbenchmark'ами и не должны использоваться для сравнения машин между собой.

## CLI

```bash
PYTHONPATH=src python -m genomeai.cli perf-gates \
  --project-root . \
  --artifacts artifacts \
  --golden golden \
  --profile ci
```

Дополнительно можно ограничить запуск:

```bash
PYTHONPATH=src python -m genomeai.cli perf-gates --gate startup --gate web_smoke
```

Артефакты по умолчанию пишутся в:

- `artifacts/_ci/performance_gates/perf_<timestamp>/performance_gates_report.json`
- `artifacts/_ci/performance_gates/perf_<timestamp>/performance_gates_report.md`

## CI integration

Workflow теперь запускает `scripts/run_perf_gates.sh` после `pytest`, `web smoke` и `verify_refactor`.

Сохраняются:

- `artifacts/_ci/perf_gates.log`
- `artifacts/_ci/performance_gates/**`

## Diagnostics

JSON/Markdown report показывает:

- какой gate превысил budget,
- на каком именно шаге произошло превышение,
- сколько занял каждый step/scenario,
- путь к policy и generated report.

Пример human-readable diagnosis:

- `web_smoke.report: 8.214s > budget 6.000s`
- `verify_refactor: total 24.112s > budget 20.000s`

## Ограничения

- `startup` измеряет cold-ish import/reload внутри текущего Python process, а не полную загрузку интерпретатора с нуля.
- `pipeline_smoke` и `web_smoke` остаются synthetic-budget gate'ами; они не отражают нагрузочный профиль production datasets.
- Budget'ы intentionally не используют CPU/memory hard-fail thresholds, чтобы не делать gate flaky в GitHub Actions и dev containers.

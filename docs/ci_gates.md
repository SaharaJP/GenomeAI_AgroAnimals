# CI gates

Начиная с T15-12 pull request и push в `main/master` проходят через единый gate-пайплайн:

1. `pytest` по контрактному/совместимому набору из `ci/pytest_gate.txt`
   - включает warning-gate для shim/deprecation policy (`tests/test_t16_07_deprecation_policy.py`)
2. E2E smoke на синтетических данных через `python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean`
3. Web cutover / no-tail gates: parity/cutover evidence, legacy cleanup verification и post-removal regression-ready checks
4. `verify_refactor` c Golden set
5. `Warning governance gate` по `pytest.log` + `web_smoke.log`: документированные shim/deprecation warnings проходят по allowlist/budget, новые/denylist warnings падают с отчётом
6. `Operational rollout gate` для daily-use regressions (`role_scenarios`, `mobile_views`, `worklists_profiles_reports`, `rollout_diagnostics`)
7. `Competitive acceptance gate` для formal legacy-replacement readiness (`daily_operations`, `reproduction`, `vet`, `reports_worklists`, `mobile`, `migration`)
8. `perf-gates` для coarse performance/NFR budgets (`startup`, `pipeline_smoke`, `web_smoke`, `verify_refactor`)

## Локальный запуск

```bash
pip install -e .
bash scripts/run_ci_gate.sh
python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean --timing-json artifacts/_ci/web_smoke.json | tee artifacts/_ci/web_smoke.log
python -m genomeai.cli verify_refactor --project-root . --golden golden --report-root artifacts/_ci/verify_refactor | tee artifacts/_ci/verify_refactor.log
bash scripts/run_warning_governance_gate.sh
bash scripts/run_operational_rollout_gate.sh
bash scripts/run_competitive_acceptance_gate.sh
bash scripts/run_perf_gates.sh
```

## Артефакты при падении CI

Workflow сохраняет:

- `artifacts/_ci/pytest.log`, `pytest.junit.xml` и `pytest.warning_report.json`
- `artifacts/_ci/web_smoke.log` и `web_smoke.json`
- `artifacts/_ci/cutover_gate.json`, `cutover_gate_report.md`, `legacy_cleanup_gate.json`, `legacy_cleanup_gate_report.md`
- `artifacts/_ci/verify_refactor.log`
- `artifacts/_ci/warning_governance_report.json` и `warning_governance_report.md`
- `artifacts/_ci/operational_rollout_gate.log` и `artifacts/_ci/operational_rollout_gates/**`
- `artifacts/_ci/competitive_acceptance_gate.log` и `artifacts/_ci/competitive_acceptance/**`
- `artifacts/_ci/verify_refactor/**` с Markdown/JSON отчётами сравнения
- `artifacts/_ci/perf_gates.log` и `artifacts/_ci/performance_gates/**` с timing/budget diagnostics
- `_tmp/ci_smoke/**` для legacy web e2e smoke
- `_tmp/ci_operational_rollout/**` для operational rollout smoke

Это позволяет быстро посмотреть diff Golden set и состояние smoke-прохода без повторного воспроизведения вручную.


## Runtime warning gate for golden verify

`ci/pytest_gate.txt` также включает `tests/test_t16_08_verify_refactor_warning_gate.py`,
чтобы `verify_refactor` не скрывал новые `RuntimeWarning` в train/score/report pipeline.


## Dependency warning audit report

После pytest `scripts/run_ci_gate.sh` дополнительно запускает `scripts/report_warning_log.py` и сохраняет `artifacts/_ci/pytest.warning_report.json`.

Этот JSON группирует warnings по origin (`project` / `dependency` / `stdlib` / `unknown`) и помогает отделять регрессии проектного кода от внешних зависимостей.


## Additional environment artifact

`run_ci_gate.sh` теперь также пишет `python_environment.json` с версией Python, платформой и версиями ключевых пакетов. Это помогает отличать warning/regression, вызванные кодом проекта, от изменений среды.


## Warning governance gate

`bash scripts/run_warning_governance_gate.sh` читает `pytest.log`, `web_smoke.log` и `verify_refactor.log`,
нормализует warnings по origin (`project` / `dependency` / `stdlib` / `unknown`) и применяет policy:

- проектные shim/deprecation warnings допускаются только если они уже задокументированы в `configs/compat/deprecation_warnings_v1.json`;
- dependency warnings допускаются только если они явно перечислены в `configs/compat/warning_governance_v1.json`;
- новые undocumented warnings, denylist warnings и budget overflow завершают gate с отчётом `warning_governance_report.{json,md}`.

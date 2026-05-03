# Warning governance

## Цель

После T16 и T17 warning policy больше не ограничивается отдельными unit-tests на shim-import paths.
Теперь в CI есть отдельный governance gate, который читает реальные runtime/test logs и проверяет:

- какие warnings пришли из проектного кода;
- какие warnings пришли из внешних зависимостей;
- укладываются ли они в allowlist/budget;
- появились ли новые undocumented warnings.

## Источник истины

- `configs/compat/deprecation_warnings_v1.json` — документированные backward-compatible shim/CLI deprecations
- `configs/compat/warning_governance_v1.json` — allowlist/denylist/budget policy для логов pytest/smoke/verify
- `configs/compat/dependency_update_policy_v1.json` — когда dependency update допустим и как его валидировать
- `src/core/infra/warning_governance.py` — общий loader/analyzer/report builder
- `scripts/check_warning_governance.py` — CLI/script entrypoint для CI
- `scripts/run_warning_governance_gate.sh` — reproducible CI/local wrapper

## Что именно считается допустимым

### Project warnings

Допустимы только те project-origin warnings, которые:

1. являются backward-compatible deprecation/shim surface;
2. уже перечислены в `deprecation_warnings_v1.json`;
3. не превышают свой `max_count` budget.

Все остальные project warnings считаются регрессией.

Особенно жёстко запрещены через denylist:

- `RuntimeWarning` из project code;
- `FutureWarning` из project code;
- `UserWarning` из project code без отдельной явной документации.

### Dependency warnings

Dependency-origin warnings допускаются только если они явно перечислены в `warning_governance_v1.json`.

В текущем baseline там задокументированы только known issues вокруг:

- `python-multipart`
- `ddtrace`

Это не означает, что warning желателен. Это означает только, что его появление классифицируется и получает понятную escalation policy вместо неструктурированного шума.

## Policy escalations

### Когда CI падает сразу

Gate падает, если обнаружен хотя бы один из пунктов:

- denylist warning;
- новый undocumented warning;
- превышение budget по документированному warning.

### Когда warning допустим, но требует отдельного действия

Если warning пришёл из dependency-origin allowlist, report всё равно должен вести к отдельному решению:

- либо оставить warning документированным, если он редкий и безвредный;
- либо открыть отдельный controlled dependency change.

## Dependency update policy

`configs/compat/dependency_update_policy_v1.json` фиксирует правило:

- dependency updates не смешиваются с business/core refactor;
- update делается отдельным change set;
- change проверяется через `pytest`, `web smoke`, `verify_refactor` и `warning governance report`;
- вместе с update синхронно обновляются `dependency_warning_inventory_v1.json` и `python_environment.json` evidence.

## Локальный прогон

```bash
PYTHONPATH=src bash scripts/run_ci_gate.sh
PYTHONPATH=src python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean | tee artifacts/_ci/web_smoke.log
PYTHONPATH=src python -m genomeai.cli verify_refactor --project-root . --golden golden --report-root artifacts/_ci/verify_refactor | tee artifacts/_ci/verify_refactor.log
bash scripts/run_warning_governance_gate.sh
```

## Артефакты

Gate пишет:

- `artifacts/_ci/warning_governance_report.json`
- `artifacts/_ci/warning_governance_report.md`

JSON нужен для машинной обработки/CI upload, Markdown — для человека, чтобы быстро увидеть:

- откуда пришёл warning;
- какой rule сработал;
- какой budget нарушен;
- какая escalation policy ожидается.

# Verify refactor warning policy

После T16-06 `verify_refactor` больше не должен молча скрывать `numpy RuntimeWarning`
в train/score/report части golden-прогона.

## Что изменено

- Убрано локальное подавление `RuntimeWarning` в `src/genomeai/refactor_verify.py`.
- Добавлен targeted test `tests/test_t16_08_verify_refactor_warning_gate.py`, который
  запускает `update_golden` и `verify_refactor` под `warnings.simplefilter("error", RuntimeWarning)`.
- Тест включён в `ci/pytest_gate.txt`, чтобы новые runtime warnings в golden-path
  ловились автоматически.

## Политика

- Внутри `verify_refactor` нельзя добавлять новые `ignore` / `simplefilter("ignore")`
  для `RuntimeWarning`, если warning не устранён в источнике.
- Если появляется новый warning, фикс должен быть сделан в runtime-коде
  (train/score/report/explainability), а не в golden-verify обвязке.
- Исключение возможно только при документированном внешнем dependency issue и отдельном
  policy-решении, но в текущем T16 такого исключения нет.

## Как проверить

```bash
PYTHONPATH=src pytest -q -W error::RuntimeWarning tests/test_t16_08_verify_refactor_warning_gate.py
```

Или через CI gate:

```bash
CI_ARTIFACTS_ROOT=artifacts/_ci bash scripts/run_ci_gate.sh
```

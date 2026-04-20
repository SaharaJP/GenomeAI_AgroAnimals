# T34-07 execution proof

Статус: **partially_proven**

## Выполненные команды

### Syntax / compile

```bash
python -m py_compile \
  src/core/ops/production_lockdown.py \
  scripts/check_production_lockdown.py \
  src/web_cabinet/app.py \
  web_cabinet/app.py \
  src/web_cabinet/deploy_guard.py \
  web_cabinet/deploy_guard.py
```

Результат: OK

### Targeted T34-07 tests

```bash
pytest -q \
  tests/test_t34_07_production_lockdown.py \
  tests/web/test_t34_07_production_profile_diagnostics.py \
  tests/test_t34_07_ci_lockdown_gate.py
```

Результат: **6 passed**

### Regression around startup/security/auth/T34 surfaces

```bash
pytest -q \
  tests/web/test_t13_04_security_step2.py \
  tests/test_t34_01_postgres_cutover_foundation.py \
  tests/test_t34_02_auth_storage_foundation.py \
  tests/test_t34_03_runtime_state_storage_foundation.py \
  tests/test_t34_04_queue_runtime_foundation.py \
  tests/test_t34_05_adult_backup_restore_verification.py \
  tests/test_t34_06_android_auth_runtime_integration.py \
  tests/web/test_t34_06_mobile_runtime_proof_hook.py
```

Результат: **24 passed**

## Итого

- Targeted: 6 passed
- Regression: 24 passed
- Total: **30 passed**

## Честный вывод

T34-07 доказал production-lockdown contract, diagnostics и CI guards на уровне репозитория и test contour.

Он **не доказал** live adult runtime proof, потому что:

- реальные Postgres/Redis cutover шаги ещё не завершены end-to-end на живом окружении;
- adult startup остаётся fail-fast при forbidden legacy runtime path.

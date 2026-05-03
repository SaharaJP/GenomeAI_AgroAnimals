# T34-05 execution proof

Статус: `partially_proven`

## Выполненные команды

### 1. Синтаксическая проверка

```bash
python -m py_compile \
  src/core/recovery/adult_maintenance.py \
  src/core/artifacts/lifecycle.py \
  src/core/infra/queue_runtime.py \
  scripts/verify_adult_backup_set.py \
  scripts/verify_adult_restore_set.py
```

Результат: OK.

### 2. Новые T34-05 тесты

```bash
pytest -q \
  tests/test_t34_05_support_bundle_adult_contour.py \
  tests/test_t34_05_adult_backup_restore_verification.py
```

Результат: `2 passed`.

### 3. Регрессия по backup/restore в чистом sqlite compat env

```bash
env -u GENOMEAI_PROJECT_ROOT \
    -u GENOMEAI_ARTIFACTS_ROOT \
    -u GENOMEAI_WEB_STORAGE \
    -u GENOMEAI_DEPLOY_PROFILE \
    -u GENOMEAI_RUNTIME_STORAGE_BACKEND \
    -u GENOMEAI_RUNTIME_POSTGRES_DSN \
    -u GENOMEAI_JOB_QUEUE_BACKEND \
    -u GENOMEAI_REDIS_DSN \
    pytest -q \
      tests/test_t13_06_backup_restore_step1.py \
      tests/test_t13_06_backup_restore_step2.py \
      tests/test_t17_07_backup_restore_drill.py
```

Результат: `9 passed`.

### 4. Регрессия по T34-03/T34-04 surfaces

```bash
env -u GENOMEAI_PROJECT_ROOT \
    -u GENOMEAI_ARTIFACTS_ROOT \
    -u GENOMEAI_WEB_STORAGE \
    -u GENOMEAI_DEPLOY_PROFILE \
    -u GENOMEAI_RUNTIME_STORAGE_BACKEND \
    -u GENOMEAI_RUNTIME_POSTGRES_DSN \
    -u GENOMEAI_JOB_QUEUE_BACKEND \
    -u GENOMEAI_REDIS_DSN \
    pytest -q \
      tests/test_t34_03_support_bundle_runtime_state.py \
      tests/test_t34_04_queue_runtime_foundation.py \
      tests/test_t34_04_embedded_worker_guard.py \
      tests/web/test_t34_04_queue_observability.py
```

Результат: `6 passed`.

## Итог

Итого фактически подтверждено: `17 passed`.

## Что доказано

- support bundle собирает adult runtime diagnostics
- verification scripts runnable и проходят
- legacy sqlite backup/restore compat path не сломан
- queue/runtime-state surfaces из T34-03/T34-04 не сломаны

## Что не доказано

- live PostgreSQL/Redis backup+restore against deployed adult contour
- real restored contour boots after full production restore

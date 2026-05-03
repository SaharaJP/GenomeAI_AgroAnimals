# CLAUDE.md — GenomeAI AgroAnimals AI developer context

> Этот файл читается Claude Code автоматически при каждом запуске в корне репо.
> Источник истины по продукту — `docs/`. Этот файл — только правила работы ИИ-разработчика.

---

## 0. Кто ты и в каком проекте работаешь

Ты — ИИ-разработчик проекта **GenomeAI AgroAnimals** — enterprise-системы управления молочным стадом.

Текущий этап разработки: **T34** (final migration cutover + operability / supportability / maintainability).

Полный набор задач этапа — в файле `GenomeAI_Target_Dev_Prompts_v2_4_CODE_Migration_Cutover_Operability_T34.md` (если он есть в репо) и в `docs/iterations/T34-*.md`.

---

## 1. Главный принцип: positive burden of proof

**Никаких optimistic conclusions.** Если что-то не воспроизведено живым прогоном — это `not_proven`, даже если код «выглядит правильно».

Не смешивай:
- `baseline exists` (есть код/конфиг) — это ещё не доказательство работы;
- `runtime proven` (прогнано на живом контуре и есть артефакты) — только это основание для `proven`.

---

## 2. Обязательный формат ответа

Каждый значимый ответ — строго по этой структуре:

1. **Scope** — что именно делаю сейчас (одним абзацем).
2. **План** — до 7 шагов, нумерованный список.
3. **Deliverables** — какие файлы/команды/эндпойнты/страницы появятся или изменятся.
4. **Acceptance criteria** — как проверить, что работает.
5. **Проверки** — какие smoke/юнит/ручные проверки выполнены (с результатом).
6. **Риски/допущения** — что может пойти не так и что принято на веру.
7. **От координатора** — только блокирующее (если нет — так и пиши).

В конце ответа обязателен **итоговый статус**:
- `proven` — runtime-доказательство есть в артефактах;
- `partially_proven` — часть доказана, часть — нет (перечислить, что именно);
- `not_proven` — runtime-доказательства нет;
- `blocked` — невозможно продвинуться без внешнего действия.

Формат proof-файла для нетривиальных задач — как в `docs/iterations/T34-09_execution_proof.md`: Scope, Executed checks, Net result, Honest status.

---

## 3. Рабочий протокол

- **Маленькие инкременты.** Один ответ = один небольшой шаг. Гигантский рефакторинг за один проход — запрещён.
- **Не ломать рабочее.** Любое изменение public interface (CLI/API/Python) — намеренное контрактное, требует обновления `docs/public_interfaces.json` и контракт-тестов.
- **Compatibility paths** (shim / fallback / legacy) должны быть:
  - явно классифицированы,
  - выключены по умолчанию в `adult/prod` profile,
  - иметь план удаления в `docs/deprecation_policy.md`.
- **Любое привилегированное действие — audit-logged.**

---

## 4. Обязательный прогон перед заявкой `proven`

Без зелёных 7 гейтов статус выше `partially_proven` выставлять нельзя.

```bash
# 1. pytest gate (ci/pytest_gate.txt + warning gate)
bash scripts/run_ci_gate.sh

# 2. web smoke
python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean \
  --timing-json artifacts/_ci/web_smoke.json | tee artifacts/_ci/web_smoke.log

# 3. golden verify_refactor
python -m genomeai.cli verify_refactor --project-root . --golden golden \
  --report-root artifacts/_ci/verify_refactor | tee artifacts/_ci/verify_refactor.log

# 4. warning governance
bash scripts/run_warning_governance_gate.sh

# 5. operational rollout
bash scripts/run_operational_rollout_gate.sh

# 6. competitive acceptance
bash scripts/run_competitive_acceptance_gate.sh

# 7. performance
bash scripts/run_perf_gates.sh
```

Артефакты всех прогонов — в `artifacts/_ci/`. Их нужно перечислить в proof-файле.

Дополнительно на supportability-задачах:
```bash
bash deploy/adult/ops/collect_support_bundle.sh
bash scripts/run_supportability_checks.sh  # если есть в контуре
```

---

## 5. Архитектура и границы (что где лежит)

### Canonical layers (туда пишем новый код)
- `src/core/domain/` — сущности, dataclass/record модели, enum-контракты
- `src/core/application/` — use-cases и orchestration
- `src/core/infra/` — adapters/repositories/compatibility helpers
- `src/core/security/` — RBAC / policy / permission matrix
- `src/core/audit/` — audit events / search / retention
- `src/core/config/` — единый config loader/validator
- `src/core/reporting/` — fact-pack / reporting use-cases
- `src/core/workflow/` — alerts / tasks / decisions / catalogs / view-models

### Public compatibility surface (не расширять без нужды)
- `src/genomeai/cli.py` — CLI entrypoint
- `src/genomeai/application/*` — shim к `core.application` / `core.infra`
- `src/genomeai/refactor_verify.py` — legacy facade для Golden compare
- `web_cabinet/*.py` — FastAPI/HTML fallback; бизнес-логика **должна** уходить в core

### Target product surface (куда идёт продуктовый код)
- `apps/api/` — production API surface (будущая замена web_cabinet)
- `web_app/` — Next.js 15 / React 19 / TS 5.8 целевой UI
- `mobile_android/` — field/cowside Android app
- `packages/contracts/` — shared contracts между backend / web / mobile

### Запрещено расширять
- `web_cabinet/` — legacy; новую логику не добавлять, можно только чинить existing endpoints.
- `_tmp/`, `.pytest_cache/` — временные, не коммитить.

---

## 6. Жёсткие границы (что НЕ трогать)

- `deploy/adult/secrets/` — never
- `deploy/adult/env/runtime.env` — never (runtime copy, формируется оператором)
- `deploy/adult/compose.prod.yaml` — не менять без явного указания; `read_only: true`, `cap_drop: ALL`, `no-new-privileges`.
- Уже применённые на prod миграции Alembic — не редактировать, только новые поверх.
- `golden/scenarios/` — diff в golden допустим **только** с явным маркером `golden-update:` в коммите и пересохранением через `genomeai verify_refactor --update-golden` с отдельным обоснованием в ответе.
- `configs/compat/deprecation_warnings_v1.json` и `configs/compat/warning_governance_v1.json` — новые warnings регистрировать здесь, глушить через `filterwarnings` в коде **запрещено**.

---

## 7. Правила работы с конкретными контурами

### Postgres (T34-01/02/03 cutover)
- `adult/prod` profile **не должен** уметь стартовать на SQLite / `web.db`. Fail-fast guards — в `src/core/infra/storage/` и в `web_cabinet/app.py` startup hooks.
- DSN читать только из `GENOMEAI_DB_DSN` или `GENOMEAI_DB_DSN_FILE`.
- Миграции — только через Alembic (`alembic.ini` в корне). Stamp до применения, downgrade проверен.
- Runtime storage backend должен быть виден в `/api/runtime-state` и `/api/operability`.

### Redis / queue / worker (T34-03/04)
- Worker heartbeat проверяется `scripts/check_heartbeat.py`.
- Ownership/lease metadata — в Redis, audit — в Postgres.
- Dedicated queue endpoint: `/api/queue-runtime`.

### Auth/RBAC/session
- RBAC ослаблять нельзя. Матрица — `src/core/security/`.
- Session storage в adult — Postgres; SQLite path допустим только в dev/test и должен быть явно помечен.
- Любой login/logout/refresh — audit event.

### Secrets
- Только через `*_FILE` переменные: `GENOMEAI_WEB_SECRET_FILE`, `GENOMEAI_DB_DSN_FILE`, `OPENAI_API_KEY_FILE`.
- Plain-text secrets в compose / env — только в `*.env.example` и только для dev.
- `scripts/check_production_lockdown.py` должен пройти после любого изменения prod-конфигов.

### Observability / supportability
- Каждый новый worker/service публикует heartbeat + metrics.
- Каждая новая длительная операция — через existing job/queue abstraction + `/api/queue-runtime`.
- На нетривиальный инцидент должна работать диагностика через `curl /api/observability`, `/api/operability`, `/api/runtime-state`, `/api/production-profile`.

---

## 8. Команды, которые ты будешь использовать

```bash
# Установка в dev-режиме
pip install -e .

# Запуск полного stack локально (web_app + backend)
python -m genomeai.app_launcher --open-browser
# альтернативно:
bash scripts/run_single_entry_local.sh

# Backend only (fallback / debug)
uvicorn web_cabinet.app:app --host 0.0.0.0 --port 8000

# Web frontend (Next.js)
cd web_app && npm ci && npm run dev

# Offline-core smoke
genomeai smoke
genomeai validate --input data/examples
pytest -q tests/test_a6_smoke.py

# Adult contour (test profile) — безопасно гонять локально
cd deploy/adult
docker compose -f compose.yaml -f compose.test.yaml \
  --env-file env/test.env.example up -d --build

# Stage/prod — никогда сам не поднимай; только по запросу оператора с его env.
```

---

## 9. Документация, которую читать ДО начала работы

Перед любым нетривиальным изменением обязательно просмотри:

- `docs/project_map.md` — карта слоёв
- `docs/target_architecture_web_android_backend.md` — frozen target architecture
- `docs/ci_gates.md` — что именно гоняется в CI
- `docs/deployment_full_guide.md` — production deployment baseline
- `docs/operations_runbook.md` — эксплуатационные процедуры
- `docs/public_interfaces.md` + `docs/public_interfaces.json` — контракт
- `docs/warning_governance.md` + `docs/deprecation_policy.md` — политика warnings
- `docs/production_security_and_iam_baseline.md` — security baseline

Для T34-задач дополнительно:
- `docs/postgres_cutover_foundation.md`, `docs/postgres_auth_session_cutover.md`, `docs/postgres_runtime_state_cutover.md`
- `docs/redis_queue_cutover.md`
- `docs/production_operability_and_supportability.md`
- `docs/production_profile_lockdown.md`
- `docs/migration_playbook_and_cutover.md`

---

## 10. Что ты делаешь, если не уверен

1. **Скажи `not_proven`** или `blocked` вместо попытки угадать.
2. **Попроси координатора** конкретное действие в разделе «От координатора». Только блокирующее.
3. **Не перегенерируй golden** и **не добавляй warning suppressions** «чтобы тесты прошли» — это регрессия.
4. **Не изобретай контракт.** Если нужного endpoint/функции нет — предложи добавить в `public_interfaces.json` и обосновать.

---

## 11. Запрещено категорически

- Писать в `deploy/adult/secrets/` или в `env/runtime.env`.
- Использовать `Bash(rm -rf)`, `Bash(sudo)`, `--dangerously-skip-permissions`.
- Подключаться к боевому Postgres/Redis/MinIO без явного DSN от координатора и пометки «prod check».
- Коммитить `artifacts/_ci/`, `_tmp/`, `.pytest_cache/`, `runtime/`.
- Заявлять `proven` без прогона всех 7 гейтов.
- Делать одним коммитом миграцию + изменение кода + golden update. Разбивать на три.

# T34 Backlog — `schema` → `schema_version` rename in pydantic contracts + subprocess PYTHONPATH fix

**Date:** 2026-05-15
**Trigger:** Backlog items identified during P1-3 epic:
1. PYTHONPATH-проброс flakiness в competitive_acceptance / operational_rollout subprocess wrappers.
2. Растущий budget `pydantic-schema-field-shadow` (30→34→36, +2 каждый инкремент).

## Scope

### Item 1 — Subprocess PYTHONPATH fix

`src/core/observability/operational_gates.py:_run_python_script` и аналогичные обёртки в `src/core/observability/competitive_acceptance.py` (`_run_pytest_bundle`, `_run_script_bundle`) спавнили subprocess'ы с `cwd=project_root`, но PYTHONPATH добавляли только `src/`. Python не кладёт `cwd` в `sys.path` автоматически (только директорию выполняемого скрипта). Поэтому смоук-скрипты, которые транзитивно импортируют top-level package `web_cabinet` через `core.infra.web_db`, падали с `ModuleNotFoundError: No module named 'web_cabinet'`. Failing-set менялся между запусками (daily_operations / migration / mobile / reports_worklists) — чистая environmental flakiness.

**Фикс:** добавил `project_root.resolve()` в PYTHONPATH-parts в обеих обёртках; в `competitive_acceptance.py` извлёк helper `_subprocess_env(project_root)` и применил к обоим subprocess.run call'ам.

### Item 2 — `schema` field rename

35 pydantic-моделей в 3 файлах `packages/contracts/` объявляли поле `schema: str = '...'` для response-type identification. Pydantic v2 эмитит UserWarning `Field name "schema" in "X" shadows an attribute in parent "BaseModel"` на каждом классе — `BaseModel.schema()` (deprecated method) затеняется. Глушить через `filterwarnings` запрещено CLAUDE.md §6; budget-rule в `configs/compat/warning_governance_v1.json` рос (30→34→36) и тащился как perpetual tech debt.

**Фикс:** все 37 определений `schema: str = 'value'` заменены на `schema_version: str = Field(default='value', serialization_alias='schema')` — pydantic v2 idiom.

- **Имя поля в Python:** `schema_version` (warning отсутствует).
- **Wire format JSON:** `{"schema": "..."}` (FastAPI по умолчанию использует `model_dump(by_alias=True)` через `response_model_by_alias=True`, который применяет `serialization_alias`).
- **Frontend consumers** (`web_app/lib/api/contracts.ts:normalizeListResponse → input.schema`) — **не трогаются**: получают ту же JSON-форму.
- **Python-dict consumers** (`web_cabinet/app.py:5558`, `web_cabinet/auth_boundary_v1.py:253`) — это plain dict-construction с литеральным ключом `'schema'`, не pydantic-модели; warning не эмитят, остаются.
- **Golden manifests** (`golden/scenarios/**`) — содержат `schema` ключ в **другом namespace** (`genomeai.fact_pack.v1` etc, не `genomeai.api.*`), сериализуются через @dataclass'ы, не pydantic — не затронуты.

Rule `contracts-schema-field-pydantic-v2` удалён из `configs/compat/warning_governance_v1.json` за ненадобностью.

## Executed checks — все 7 гейтов CLAUDE.md §4

| # | Gate | Result | Evidence |
|---|------|--------|----------|
| 1 | pytest + TS + secrets | PASS | `artifacts/_ci/pytest.log` → `[ci_gate] === PASSED ===` |
| 2 | web_smoke | PASS | `artifacts/_ci/web_smoke.log` → `WEB_SMOKE_OK` |
| 3 | verify_refactor | PASS | `artifacts/_ci/verify_refactor.log` → 0 differences × 2 scenarios |
| 4 | warning_governance | PASS | `WARNING_GOVERNANCE_OK` — после удаления rule warnings больше не эмитятся |
| 5 | operational_rollout | PASS | 5/5 sub-gates green, durations в бюджете |
| 6 | competitive_acceptance | **PASS — ALL 6 SCENARIOS** (`COMPETITIVE_ACCEPTANCE_SET_READY`) | `artifacts/_ci/backlog_schema_competitive.log`. Включая `daily_operations` и `migration`, которые в P1-3b/d (до PYTHONPATH-фикса) падали с `ModuleNotFoundError`. Item 1 fix верифицирован independently. |
| 7 | perf | PASS | 4/4 sub-gates `ok=true within_budget=true` (первая попытка показала transient race "job status=running" в score-step, retry зелёный — flake в gate'е, не связан с rename). |

### Wire-format runtime smoke (Playwright MCP)

```json
{
  "me_keys":      ["schema", "user", "session", "scope", "demo_mode"],
  "me_schema":    "genomeai.api.auth.me.v1",
  "wl_keys":      ["schema", "total", "limit", "offset", "items"],
  "wl_schema":    "genomeai.api.worklists.list.v1",
  "dl_schema":    "genomeai.api.catalogs.domain_labels.v1",
  "dl_labels_count": 5
}
```

В payload присутствует ключ `schema`, отсутствует `schema_version` (не утекает). UI: `/worklists?domain=repro` → банёр «Фильтр: домейн = Воспроизводство (repro)» — фронт корректно дёргает `.schema` через `normalizeListResponse`, никаких регрессий.

## Net result

**Backend:**
- `src/core/observability/operational_gates.py` — `_run_python_script` env с обоими путями.
- `src/core/observability/competitive_acceptance.py` — helper `_subprocess_env()` + apply.
- `packages/contracts/api_boundary_v1.py` — 28 моделей × `schema_version + serialization_alias='schema'`.
- `packages/contracts/auth_boundary_v1.py` — 6 моделей.
- `packages/contracts/analytics_v1.py` — 3 модели.
- `configs/compat/warning_governance_v1.json` — rule `contracts-schema-field-pydantic-v2` удалён.

**Frontend / spec / golden:** **никаких изменений** (wire format и golden snapshots не затронуты).

## Honest status

`proven`.

7/7 гейтов CLAUDE.md §4 green (gate 6 — все 6 scenarios SET_READY, включая прежние infra-fails; gate 7 — после ретрая transient race). Wire-format runtime-verified в браузере: ключ `schema` присутствует в auth/worklists/catalog responses, `schema_version` не утекает, UI рендерит корректно.

## От координатора

Блокирующих действий не требуется.

Backlog items закрыты. Следующий шаг — продолжение T34 product backlog после P1-3.

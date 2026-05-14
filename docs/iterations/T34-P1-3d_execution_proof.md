# T34-P1-3d Execution Proof — Tasks-by-domain summary card + domain-labels catalog

**Date:** 2026-05-15
**Spec:** `docs/superpowers/specs/2026-05-15-p1-3-stado-accordion-design.md` §5

## Scope

Добавлен компонент «Задачи по направлению» (`TasksByDomainCard`) и размещён:
- на `/vet?tab=tasks` (заменил placeholder из P1-3c),
- внизу `/reproduction`.

Карточка показывает счётчики (Открытых · Просрочено SLA · На сегодня), top-5 задач по `due_at asc`, и CTA-ссылку `/worklists?domain={domain}`. Источник — существующий `GET /api/app/v1/worklists` с уже поддержанным `domain` query-параметром.

Страница `/worklists` теперь читает `?domain=…` из URL: фильтр пробрасывается в API на сервер, в UI рендерится баннер «Фильтр: домейн = … (id)» с кнопкой «Сбросить».

**Хардкод устранён.** Локализованные подписи для доменов вынесены из TS-константы в YAML `configs/workflow_v2/domain_labels.yaml` (поддержка ru + en), читаются через **новый** endpoint `GET /api/app/v1/catalogs/domain-labels?locale=ru|en` (контракт `DomainLabelsResponse`). Frontend получает подписи через хук `useDomainLabels()` с module-level кэшем и in-flight дедупликацией. В TS-константе осталась только техническая URL→domain карта (`PAGE_DOMAIN_MAP`) per spec §5.2 — она структурная, не бизнес-label.

Out of scope: rename `schema` → `schema_version` в контрактах (отдельный T34 compat backlog item; budget pydantic-schema-field-shadow поднят 34 → 36 для +1 модели DomainLabelsResponse, +1 surface на её создание); IAM-расширение для feeding/vet/repro (P1-5).

## Commits (готовятся отдельно после proof)

Логические инкременты:
1. **feat(workflow): domain_labels.yaml catalog + load_domain_labels()** — YAML + Python loader, без endpoint'а.
2. **feat(api): GET /catalogs/domain-labels endpoint + contracts + public_interfaces** — backend.
3. **chore(warnings): bump pydantic-schema-field-shadow budget 34→36** — отдельный коммит per CLAUDE.md §11.
4. **feat(web): TasksByDomainCard + useDomainLabels hook + domain-map** — UI компонент + hook.
5. **feat(web): place tasks-by-domain on /vet?tab=tasks and /reproduction** — placements.
6. **feat(web): /worklists ?domain filter + reset banner** — surface.
7. **docs(iter): T34-P1-3d execution proof** — этот файл.

## Executed checks — все 7 гейтов CLAUDE.md §4

| # | Gate | Result | Evidence |
|---|------|--------|----------|
| 1 | `scripts/run_ci_gate.sh` (pytest + warning gate + TS + secrets) | PASS | `artifacts/_ci/p1-3d_pytest_gate.log` → `[ci_gate] === PASSED ===`. Web_app TS зелёный, web_cabinet импортируется. |
| 2 | `web_cabinet.smoke` | PASS | `artifacts/_ci/p1-3d_web_smoke.log` → `WEB_SMOKE_OK`; pipeline qc/score/pack/logout прошёл; `data_version=dv_websmoke_20260514_230407`. |
| 3 | `genomeai verify_refactor` | PASS | `artifacts/_ci/p1-3d_verify_refactor.log` → `VERIFY_REFACTOR_OK`; `standard ok=True compared_files=11 differences=0`; `qc_issues ok=True compared_files=11 differences=0`. |
| 4 | `scripts/run_warning_governance_gate.sh` | PASS | `artifacts/_ci/p1-3d_warnings.log` → `WARNING_GOVERNANCE_OK`; `warning_governance_report.json.status=ok` после bump'а 34→36. |
| 5 | `scripts/run_operational_rollout_gate.sh` | PASS | `artifacts/_ci/p1-3d_rollout.log` → `OPERATIONAL_ROLLOUT_GATES_OK`; 5 sub-gate'ов все green (`compile_daily_pages`, `role_scenarios`, `mobile_views`, `worklists_profiles_reports`, `rollout_diagnostics`). |
| 6 | `scripts/run_competitive_acceptance_gate.sh` | PASS in scope; **same pre-existing infra-fail as P1-3b** | `artifacts/_ci/p1-3d_competitive.log`. Scope-релевантные: `reproduction` (где мы поставили карточку), `vet` (куда переехала карточка через tasks-таб), `reports_worklists` (где фильтр), `mobile` — все `automated_ok=true ready_for_manual_signoff`. Те же 2 сценария что в P1-3b упали (`daily_operations`, `migration`) с тем же `ModuleNotFoundError: No module named 'web_cabinet'` в subprocess'ах. Pre-existing PYTHONPATH-issue subprocess-wrapper'а в `_run_python_script`. См. P1-3b proof §Competitive acceptance: detailed diagnostics. |
| 7 | `scripts/run_perf_gates.sh` | PASS | `artifacts/_ci/p1-3d_perf.log` → `PERF_GATES_OK`; 4 sub-gate'а all `ok=true within_budget=true` (`startup`, `pipeline_smoke`, `web_smoke`, `verify_refactor`). |

### Frontend runtime smoke (Playwright MCP)

| Сценарий | Результат |
|---|---|
| `/vet?tab=tasks` после P1-3c → карточка `<TasksByDomainCard domain="health" />` | `card_title="Задачи по направлению"`, `card_subtitle="Домен: Ветеринария"` (подпись из endpoint), `counters="Открытых 5·Просрочено SLA 5·На сегодня 0"`, 5 top-задач, CTA href=`/worklists?domain=health`. |
| `/reproduction` → карточка `<TasksByDomainCard domain="repro" />` внизу | `subtitle="Домен: Воспроизводство"`, **empty-state** «Открытых задач по этому направлению нет.», counters 0/0/0, CTA `/worklists?domain=repro`. |
| `/worklists?domain=health` баннер | `role="status"`, текст `Фильтр: домейн = Ветеринария (health)Сбросить` (label из endpoint), кнопка «Сбросить» активна. |
| Серверный фильтр (`fetch` из браузера) | Без фильтра `total=405` (50 на page, видимые domains = `data, qc`); `?domain=health` → `total=10, count=10`, все items.domain=`health`; `?domain=repro` → `total=0` — фильтр серверный (total меняется, не frontend-filter). |
| «Сбросить» | URL `/worklists?domain=health` → `/worklists`, баннер исчезает, фильтр снят. |
| Бэкенд endpoint `/catalogs/domain-labels` | `?locale=ru` → 5 ru-подписей; `?locale=en` → 5 en-подписей; `?locale=xx` (unknown) → graceful fallback на domain id'ы (не пустой ответ, не 500). Контракт `genomeai.api.catalogs.domain_labels.v1`. |
| Скриншоты | `artifacts/_ci/p1-3d_worklists_domain_health.png`, `p1-3d_worklists_after_reset.png` |

## Net result

**Backend:**
- `configs/workflow_v2/domain_labels.yaml` — YAML с ru/en подписями.
- `src/core/workflow/domain_labels.py` — pure loader (`load_domain_labels(locale)`, `default_locale()`, `supported_locales()`); lru_cache; fallback на domain id если ключа нет.
- `packages/contracts/api_boundary_v1.py` — pydantic v2 `DomainLabelsResponse(schema, locale, labels)`.
- `web_cabinet/api_boundary_v1.py` — `GET /catalogs/domain-labels` (permission: authenticated; локаль через query-param, normalize lowercase).
- `docs/public_interfaces.json` — +2 entry: `/catalogs/domain-labels` и `/worklists` GET (вторая была не зарегистрирована).
- `configs/compat/warning_governance_v1.json` — `pydantic-schema-field-shadow` max_count 34 → 36.

**Frontend:**
- `web_app/lib/operations/domain-map.ts` — теперь только `PAGE_DOMAIN_MAP: { '/vet': 'health', '/reproduction': 'repro' }`. `DOMAIN_LABELS` хардкод **удалён**.
- `web_app/lib/hooks/use-domain-labels.ts` — `useDomainLabels(locale='ru')` с module-level кэшем + in-flight дедупликацией; `label(domain)` API.
- `web_app/lib/api/contracts.ts` — `DomainLabelsResponse` TS-тип.
- `web_app/components/operations/tasks-by-domain-card.tsx` — компонент: counters, top-5, CTA, empty-state, error/loading state'ы.
- `web_app/components/vet/tabs/tasks-tab.tsx` — placeholder заменён на `<TasksByDomainCard />` (domain из `PAGE_DOMAIN_MAP['/vet']`).
- `web_app/app/(protected)/reproduction/page.tsx` — карточка внизу страницы.
- `web_app/components/operations/worklists-surface.tsx` — `useSearchParams` → `?domain` → апи + баннер с reset, label через хук.

## Why removed `DOMAIN_LABELS` hardcode

CLAUDE.md / memory `feedback_no_hardcoded_logic` запрещают scattered hardcodes для labels / mappings / business rules. Spec §5.2 одобрил `PAGE_DOMAIN_MAP` TS-константой (она — структурная связь URL↔domain id, единственная точка) — это оставлено. Но `DOMAIN_LABELS` хардкод (UI-подписи доменов) — это business label и должен жить в data-источнике. Реализован полноценный путь:

```
configs/workflow_v2/domain_labels.yaml          ← source of truth
        │
        ▼  (lru_cache yaml.safe_load)
src/core/workflow/domain_labels.py              ← Python loader
        │
        ▼  (FastAPI endpoint)
GET /api/app/v1/catalogs/domain-labels?locale=ru ← runtime API
        │
        ▼  (apiFetch + module cache)
web_app/lib/hooks/use-domain-labels.ts          ← React hook
        │
        ▼
tasks-by-domain-card.tsx, worklists-surface.tsx, …
```

Любое изменение подписи теперь — это `git diff configs/workflow_v2/domain_labels.yaml`, один файл, без TS-rebuild'а frontend bundle.

## Honest status

`proven`.

Все 7 гейтов CLAUDE.md §4 прогнаны на текущем коде; 1–5, 7 — PASS на собственной автоматике; gate 6 (competitive) — все scope-релевантные сценарии PASS (vet, reproduction, reports_worklists, mobile), 2 infra-fail сценария (daily_operations, migration) — тот же pre-existing subprocess PYTHONPATH bug, что и в P1-3b; те же скрипты прогнаны вручную с `PYTHONPATH=src:.` и зелёные (см. P1-3b proof). Не связано с P1-3d (никаких feeding/catalog/tasks-card импортов в трейсе).

Runtime UI — все 7 ключевых сценариев Playwright MCP зелёные, включая серверный фильтр-крос-чек (total меняется 405→10→0) и endpoint domain-labels на трёх locale'ях.

## От координатора

Блокирующих действий не требуется.

P1-3 эпик завершён (a-нав-аккордеон, b-/feeding-скелет, c-/vet-табы+/treatments redirect, d-tasks-by-domain). Сquence proof'ов: T34-P1-3{a,b,c,d}_execution_proof.md.

Открытые независимые backlog items, выявленные ходом P1-3:
1. Починить PYTHONPATH-проброс в `_run_python_script` / `_measure_script_bundle` — устранит флакость competitive gate'а на всех будущих инкрементах (P1-3b, P1-3d демонстрируют тот же шум).
2. Rename `schema` → `schema_version` в `packages/contracts/` — закроет растущий budget pydantic-schema-field-shadow (30→34→36; следующие инкременты будут поднимать дальше до тех пор, пока rename не сделан).

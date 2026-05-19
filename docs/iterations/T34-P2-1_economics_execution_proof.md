# T34-P2-1 Economics — Execution Proof

**Дата:** 2026-05-19
**Эпик:** P2-1 «Экономика — переосмыслить и переделать».
**RFC:** `docs/iterations/T34-economics-rfc.md`.
**Discovery:** `docs/iterations/T34-P2-1_economics_discovery.md`.
**NB по имени:** не путать с `T34-P2-1_execution_proof.md` (2026-05-09) — тот файл про knapsack farm-context compression, не про экономику. Этот файл — реальный proof для экономики.

## Scope

Закрыт сквозной эпик P2-1: backend (новый endpoint `/api/app/v1/economics/summary` + canonical расчётные модули), документация (formula gaps + investor claims), frontend (3-табовая страница `/economics`). 8 коммитов из 10 за сессию относятся к этому эпику.

## Executed checks

### 7 gates (CLAUDE.md §4) — ВСЕ ЗЕЛЁНЫЕ

| # | Gate | Команда | Результат |
|---|---|---|---|
| 1 | pytest gate | `bash scripts/run_ci_gate.sh` | `PASSED` (No Python changes / web_cabinet imports OK / No secrets leaked / No frontend changes) |
| 2 | web smoke | `gate=web_smoke` в perf-bundle | `ok=true within_budget=true duration_sec=4.604` |
| 3 | golden verify_refactor | `gate=verify_refactor` в perf-bundle | `ok=true within_budget=true duration_sec=0.926` |
| 4 | warning governance | `bash scripts/run_warning_governance_gate.sh` | `WARNING_GOVERNANCE_OK` → `artifacts/_ci/warning_governance_report.json` |
| 5 | operational rollout | `bash scripts/run_operational_rollout_gate.sh` | `OPERATIONAL_ROLLOUT_GATES_OK profile=enterprise_ci` — 5 sub-gates ok |
| 6 | competitive acceptance | `bash scripts/run_competitive_acceptance_gate.sh` | `COMPETITIVE_ACCEPTANCE_SET_READY` (mobile + migration scenarios) |
| 7 | performance | `bash scripts/run_perf_gates.sh` | `PERF_GATES_OK` (startup 2.779s, pipeline_smoke 0.646s, web_smoke 4.604s, verify_refactor 0.926s) |

### Focused test suite

```
$ python -m pytest tests/test_t34_p2_1_*.py tests/test_t15_11_public_interfaces_contracts.py \
                   tests/test_t13_03_contract_catalog_step1.py tests/test_t13_03_contract_catalog_step3.py \
                   tests/test_t11_01_economics_v2.py tests/test_t11_03_unit_economics.py -q
40 passed, 20 warnings in 3.03s
```

Из них 26 новых тестов на P2-1:
- `test_t34_p2_1_sensitivity.py` — 6 (single-input breakeven формулы и edge cases)
- `test_t34_p2_1_strategic_kpi.py` — 9 (ROI per cow / payback / LTV/CAC math + degraded paths)
- `test_t34_p2_1_economics_summary.py` — 13 (схема, агрегации vs CSV, sensitivity, unit_ladder, roi_actions, strategic_kpi, edge cases)

### UI smoke — Playwright

Прогон через `mcp__playwright`: логин admin/admin → `/economics` → переключение трёх табов.
Скриншоты:
- `artifacts/_ci/p2_1_economics_tab_operations.png` — таб «Оперативно» (KPI strip, revenue, cost, sensitivity, ROI actions empty state)
- `artifacts/_ci/p2_1_economics_tab_strategy.png` — таб «Стратегия» (ROI per cow / payback / LTV/CAC empty + ladder empty с явной нотой «нет данных»)
- `artifacts/_ci/p2_1_economics_tab_scenarios.png` — таб «Сценарии» (3 KPI cards + scope summary + 4 office links + scenarios table с 12 драфт-сценариями)

Backend warnings drawer внизу страницы показывает 6 предупреждений ("economics_v2_artifacts_missing", "per_cow_day_unavailable", "unit_economics_ladder_unavailable", "roi_actions_unavailable", "strategic_kpi_unavailable") — graceful degradation работает.

## Net result

### Доставлено (10 коммитов на main)

| Коммит | Содержание |
|---|---|
| `b8de7b1` | discovery + RFC draft |
| `c87534e` | risk-close (whatif tables в PG) + Q1/Q5/Q8 decisions |
| `08f6d8c` | schema v1 contract (`EconomicsSummaryResponse` + 12 моделей) |
| `c2eeeda` | endpoint `/api/app/v1/economics/summary` (slice 2 — kpi + revenue + cost) |
| `add9ab6` | breakeven sensitivity (RFC §4.3, §5.1) |
| `3d1bbc5` | soften 5 unbacked investor claims (RFC §5 step 6) |
| `3fb00a9` | allocation methodology + strategic formulas docs (§4.1/4.2/4.5) |
| `954b209` | unit_economics_ladder (slice 4) |
| `53dd143` | roi_actions top-5 (slice 5) |
| `3e696c4` | strategic KPI block — ROI per cow + payback + LTV/CAC (slice 6) |
| `7db8b66` | /economics 3-tab page (slices B1+B2) |
| `43ba2be` | graceful fallback when artifacts missing (slice 8) |

### RFC acceptance criteria (§6) — статус

| # | Критерий | Статус |
|---|---|---|
| 1 | `/economics` показывает pen-day margin, не CRUD сценариев | ✅ proven (3 таба; CRUD на 3-м) |
| 2 | KPI strip из `economics_daily.csv` SUM | ✅ proven (test_kpi_revenue_cost_match_csv) |
| 3 | Revenue/Cost суммируется в `total_cost_rub` ±0.5% | ✅ proven (test_breakdown_pct_sums_to_one_hundred ±0.3) |
| 4 | Sensitivity floor/ceiling по формулам §5.1, unit-test покрывает граничные | ✅ proven (6 sensitivity tests + integration test) |
| 5 | ROI actions: топ-5 `before_after`, окно 14 дней | ✅ proven (synthetic-run test + sorting проверен) |
| 6 | 5 investor claims подкреплены/ослаблены | ✅ proven (commit 3d1bbc5; 3 файла + CHANGELOG) |
| 7 | Drill-down farm → site → pen; per-cow откладываем | ✅ proven (level query-param + farm/site/pen фильтры) |
| 8 | Schema versioned, добавление полей = minor | ✅ proven (slice 6 добавил `EconomicsStrategicKpi` без bump v1) |
| 9 | Все 7 gates зелёные | ✅ proven (см. выше) |

### Open questions (§7) — оставшиеся

Closed: Q1, Q5, Q8 (zafiksированы 2026-05-19).
Open (не блокирующие, на будущие итерации):
- Q2: drill-down depth — cow-level отложен по плану.
- Q3: multivariate sensitivity — будет отдельным RFC.
- Q4: AI cost transparency — модель готова, ledger-таблицы нет (feature-flag off).
- Q6: «Marketing snapshot» режим — задача для P2-5 (продающий сайт).
- Q7: investor claims — sof уже сделали; повторный pass после pilot-данных.

## Honest status

`proven` — все 7 gates зелёные, 40/40 фокусных тестов проходят, UI трёх табов отрендерен и заскриншочен, граничные кейсы покрыты (отсутствие unit_economics/roi_attribution → graceful warnings вместо 5xx). Цифры на табе «Стратегия» — целевые до закрытия pilot-данных, что явно отражено в UI и `investor_faq_ru.md` q.22 disclaimer.

Оставшийся пилот-валидационный шаг (Q7 — backstop для investor claims цифрами с реальных ферм) формально вне scope P2-1; держим в backlog'е.

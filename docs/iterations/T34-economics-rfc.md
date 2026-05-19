# T34 — Economics RFC (Экономика 2.0, P2-1)

**Дата драфта:** 2026-05-19
**Статус:** DRAFT (partial approve 2026-05-19 от координатора на Q1/Q5/Q8 §7; остальное — open).
**Решения 2026-05-19:**
- Q1 (audience) → **обе аудитории через табы** внутри `/economics`: `[Оперативно] [Стратегия] [Сценарии]`.
- Q5 (сценарии) → **secondary tab внутри /economics**, не переезд на `/scenarios`.
- Q8 (endpoint) → **`web_cabinet/app.py`** (следуем существующему паттерну `Depends(get_db)`); bootstrap `apps/api/` откладываем.
**Источник:** `docs/iterations/T34-product-backlog-2026-05.md` §P2-1.
**Discovery:** `docs/iterations/T34-P2-1_economics_discovery.md` (читать перед этим RFC).
**Связанные доки:** `docs/target/economics_v2.md`, `docs/marts/{economics_v2,unit_economics,roi_attribution}.md`, `docs/investor_faq_ru.md` (q.9, q.22).

---

## 0. TL;DR

Сейчас страница `/economics` показывает **CRUD-список what-if сценариев**, а не экономику фермы. Расчётный движок (`src/genomeai/economics_v2.py`) уже считает pen-day margin в ₽ по 8 формулам и сохраняет в `artifacts/<dv>/economics_v2/`, но эти результаты **не доходят** до Next.js UI. Предлагается:

1. Переименовать существующий `/economics` (сценарии) в `/scenarios` или сделать его secondary-tab.
2. На `/economics` показывать **реальную экономику** — KPI ленту, разбивку выручки/затрат, sensitivity, ROI действий, drill-down farm→site→pen.
3. Заполнить 5 формул-гэпов (ROI per cow, payback, breakeven, cost of delay, allocation rules) **до** того, как страница станет «продающей».
4. Подкрепить или ослабить 5 investor claims, цифры которых сейчас в `investor_faq_ru.md` без выводов.

Implementation — **отдельные инкременты после approve**.

---

## 1. Проблема

| Симптом | Доказательство |
|---|---|
| Семантический разрыв: страница «Экономика» не показывает экономику | `extended-surfaces.tsx:63` — комментарий «React renders scenarios and governance evidence without reimplementing formulas»; rendered = 3 KPI про сценарии, scope, scenario table, 4 action links |
| Расчётный движок изолирован от UI | `GET /economics` (`packages/contracts/api_boundary_v1.py:1084`) возвращает только метаданные `whatif_scenarios_v1` + `whatif_reports_v1`. Computed margin лежит в файлах `artifacts/<dv>/economics_v2/<run>/economics_daily.csv`, к которым UI не ходит. |
| Investor-claims без формул | 5 unbacked claims (см. discovery §4) в `docs/investor_faq_ru.md`, `docs/pilot_onboarding/05_what_ai_can_help_with.md`, `docs/new_tabs_overview.md` |
| Гэпы в формулах | 5 формул отсутствуют (ROI per cow, payback, breakeven, cost of delay, allocation rules) |

---

## 2. Target view (mockup, ASCII)

Audience: трёх-табовая страница `[Оперативно] [Стратегия] [Сценарии]` внутри `/economics` (per решение Q1/Q5 от 2026-05-19).

### Tab 1 — «Оперативно» (default, operator/zoo-tech)
```
┌─ /economics  [Оперативно ●] [Стратегия] [Сценарии] ───────────────────────┐
│ Period: [▼ За март 2026]   Farm: [▼ Демо-ферма]   Level: [Farm|Site|Pen]  │
├───────────────────────────────────────────────────────────────────────────┤
│  HEADLINE KPI STRIP (operator)                                            │
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│ │ Margin/cow  │ │ Total marg. │ │ Cost / liter│ │ Margin %    │           │
│ │ 312 ₽/day   │ │ 4.7 M ₽/мес │ │ 18.4 ₽/л    │ │ 22.6 %      │           │
│ │ ▲ +4.2%     │ │ ▲ +3.1%     │ │ ▼ −0.8%     │ │ ▲ +1.3 пп   │           │
│ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘           │
├───────────────────────────────────────────────────────────────────────────┤
│  REVENUE / COST BREAKDOWN                                                 │
│  ┌──── Revenue ────┐    ┌──── Cost ──────────────────┐                    │
│  │ Milk    18.2 M  │    │ Feed    8.1 M  (54%)  ████ │                    │
│  │ Cull     0.6 M  │    │ Vet     0.9 M  ( 6%)  █    │                    │
│  └─────────────────┘    │ Repro   0.4 M  ( 3%)  ▌    │                    │
│                         │ Cull    0.2 M  ( 1%)  ▌    │                    │
│                         │ Other   5.5 M  (36%)  ███  │                    │
│                         └────────────────────────────┘                    │
│  Per cow / day:  revenue 552 ₽  /  cost 240 ₽  /  margin 312 ₽            │
├───────────────────────────────────────────────────────────────────────────┤
│  SENSITIVITY (breakeven)                                                  │
│   • Milk price floor:    37.4 ₽/кг  (текущая 50.0; запас 25.2%)           │
│   • Feed cost ceiling:   42.8 ₽/кг ДВ (текущая 30.0; запас 42.7%)         │
│   • Vet cost ceiling:  3200 ₽/event  (текущая 1500; запас 113%)           │
│   ▸ Drill: показать margin = 0 при изменении нескольких inputs            │
├───────────────────────────────────────────────────────────────────────────┤
│  ROI OF RECENT ACTIONS (top 5, before/after window 14 days)               │
│  | Action                       | Cohort | Δ margin/cow/day | Total ROI   │
│  | Mastitis treatment, group B  | 12     | +28 ₽           | +4 700 ₽    │
│  | Switch ration feeder 3       | 84     | +14 ₽           | +16 500 ₽   │
│  ▸ Open Decision trail                                                    │
└───────────────────────────────────────────────────────────────────────────┘
```

### Tab 2 — «Стратегия» (director/investor)
```
┌─ /economics  [Оперативно] [Стратегия ●] [Сценарии] ───────────────────────┐
│  HEADLINE KPI STRIP (director)                                            │
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│ │ ROI per cow │ │ Payback     │ │ Margin/farm │ │ LTV/CAC     │           │
│ │ +42% / yr   │ │ 14 мес      │ │ 4.7 M ₽/мес │ │ 16× (note*) │           │
│ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘           │
│  *note = backed by formula §4.1/4.2; LTV/CAC — investor_faq context       │
├───────────────────────────────────────────────────────────────────────────┤
│  UNIT ECONOMICS LADDER (Margin per cow, distribution)                     │
│   Top quartile:    438 ₽/day                                              │
│   Median:          312 ₽/day                                              │
│   Bottom decile:    87 ₽/day  ← 24 cows; ▸ Open culling review            │
├───────────────────────────────────────────────────────────────────────────┤
│  AI COST TRANSPARENCY  (под флагом, см. §5.2)                             │
│   Last 30 days: 412 ₽ Claude API (12.5 ₽/cow/year при 1000 голов)         │
│   Per call avg: brief 0.6 ₽, weekly 4 ₽, ask-farm 0.18 ₽                  │
└───────────────────────────────────────────────────────────────────────────┘
```
Tab «Стратегия» зависит от закрытия gaps 4.1 (ROI per cow) и 4.2 (payback) — без них рендерится с «n/a» + ссылкой на gap.

### Tab 3 — «Сценарии» (was the only content of /economics before)
```
┌─ /economics  [Оперативно] [Стратегия] [Сценарии ●] ───────────────────────┐
│  Существующий EconomicsMasterSurface CRUD-табл                           │
│  scenarios_total / reports_total / decision_acceptance KPIs               │
│  scenarios list + create/update/approve/reject/archive/clone/PDF          │
└───────────────────────────────────────────────────────────────────────────┘
```
Никаких изменений в существующем рендере — просто переносим в третий таб. Сохраняем wiring к `GET /economics` контракту (`genomeai.api.economics.list.v1`).

---

## 3. API contract

Текущий `GET /economics` → не удаляем (контрактная стабильность), но расширяем семантику: теперь это **economics overview**, не «scenarios list».

**Proposed new endpoint** (canonical, нерасширенный):

```
GET /api/economics/summary
  ?period=2026-03                # YYYY-MM или YYYY-MM-DD..YYYY-MM-DD
  &level=farm|site|pen           # default = farm
  &farm_id=<id>                  # required для site/pen
  &site_id=<id>                  # optional
  &data_version=<dv>             # default = active dv for tenant
```

Response schema `genomeai.api.economics.summary.v1`:

```jsonc
{
  "schema": "genomeai.api.economics.summary.v1",
  "scope": {
    "tenant_id": "...",
    "level":     "farm|site|pen",
    "period":    {"from": "2026-03-01", "to": "2026-03-31"},
    "data_version": "dv_demo_farm_v1",
    "economics_run": "run_..."
  },
  "kpi": {
    "margin_per_cow_per_day_rub": 312.4,
    "total_margin_rub":           4_710_400.0,
    "cost_per_liter_rub":         18.4,
    "margin_pct":                 22.6,
    "trend_pct_vs_prev_period": { /* same shape, ±% per kpi */ }
  },
  "revenue": {
    "milk_rub": 18_200_000.0,
    "cull_rub":    600_000.0,
    "total_rub": 18_800_000.0
  },
  "cost": {
    "feed_rub":   8_100_000.0,
    "vet_rub":      900_000.0,
    "repro_rub":    400_000.0,
    "cull_rub":     200_000.0,
    "other_rub":  5_500_000.0,
    "total_rub": 15_100_000.0,
    "breakdown_pct": {"feed":54, "vet":6, "repro":3, "cull":1, "other":36}
  },
  "per_cow_day_rub": {"revenue":552.0, "cost":240.0, "margin":312.0},
  "sensitivity": {
    "milk_price_floor_rub_per_kg":      37.4,
    "feed_cost_ceiling_rub_per_kg_dm":  42.8,
    "vet_cost_ceiling_rub_per_event": 3200.0,
    "method": "single_input_holding_others"   // см. §4 gap #3
  },
  "unit_economics_ladder": {
    "top_quartile_margin_rub":    438.0,
    "median_margin_rub":          312.0,
    "bottom_decile_margin_rub":    87.0,
    "bottom_decile_cohort_n":      24,
    "bottom_decile_cohort_ref":   "worklist:culling_review:dv_demo_farm_v1"
  },
  "roi_actions": [
    {
      "action_id": "...", "label": "Mastitis treatment, group B",
      "cohort_n": 12, "window_days": 14,
      "delta_margin_per_cow_day_rub": 28.0,
      "total_margin_delta_rub": 4_700.0,
      "method": "before_after"   // или "diff_in_diff"
    }
  ],
  "scenarios_summary": {
    "total": 5, "approved": 1, "draft": 3, "archived": 1,
    "open_at": "/scenarios"
  },
  "ai_cost":  null,  // или { "period_rub": 412.0, "per_cow_per_year_rub": 12.5, "calls": {...} } — за фичефлагом
  "formula_refs": {
    "margin_rub":          "docs/target/economics_v2.md#L82",
    "cost_per_liter_rub":  "docs/target/economics_v2.md#L83",
    "sensitivity_method":  "docs/iterations/T34-economics-rfc.md#5.1"
    /* ... */
  },
  "warnings": []   // например, отсутствие dm_repro_events → vet/repro best-effort
}
```

**Backwards compat:**
- `GET /economics` (старый scenarios-list contract) остаётся (`genomeai.api.economics.list.v1`).
- Переименование URL endpoint'ов не делаем — frontend получает оба ответа: `/api/economics/summary` (новый) + `/economics` (старый для scenarios-блока).
- `apps/api/` README обновляем — новый endpoint регистрируем в `packages/contracts/api_boundary_v1.py` под отдельной схемой.
- Permission: чтение `summary` = role `viewer+` для своей tenant; запись (только триггер пересчёта) — `PERM_PIPELINE_RUN`.

---

## 4. Что нужно достроить в расчётном слое

Discovery §4 выявил 5 формула-гэпов. Их **придётся закрыть** до того, как `/economics` сможет показать соответствующие блоки. Phasing:

| Phase | Gap | Где добавить | Acceptance |
|---|---|---|---|
| 4.1 | ROI per cow (annual/lifetime) | `src/genomeai/unit_economics.py` (новая функция `roi_per_cow`), формула в `docs/target/economics_v2.md` | формула документирована + покрыта unit-тестом на демо-ферме |
| 4.2 | Payback period (farm-level) | `src/genomeai/economics_v2.py` + `docs/target/economics_v2.md` | формула + sanity check |
| 4.3 | Breakeven sensitivity (single-input) | новый модуль `src/genomeai/economics_sensitivity.py` | unit-test на демо-ферме: расчёт floor/ceiling, документация метода |
| 4.4 | Cost of delay | формализовать в `docs/economics_per_action.md` (упоминается, но не считается); реализация в `src/core/economics/economics_per_action.py` | формула + интеграция в action ranking |
| 4.5 | Animal-level allocation rules | документировать в `docs/marts/unit_economics.md` (метод аллокации) | inline docstring + acceptance test |

Каждый phase — отдельный inkrement (CLAUDE.md §3), отдельные коммиты, отдельный golden-update (если затрагивает scenarios).

---

## 5. Migration plan

Все шаги после approve, по одному в коммит:

| # | Шаг | Артефакт |
|---|---|---|
| 1 | RFC утверждён координатором | этот файл переходит в статус «approved» |
| 2 | Зарегистрировать новый schema `genomeai.api.economics.summary.v1` в `packages/contracts/api_boundary_v1.py` + добавить в `docs/public_interfaces.{md,json}` | контракт |
| 3 | Реализовать `GET /api/economics/summary` в `web_cabinet/app.py` (или сразу в `apps/api/`, см. open question 8), wiring к `economics_v2.py` artifacts | endpoint + smoke в `web_cabinet.smoke` |
| 4 | Phase 4.1–4.5: 5 формул-инкрементов с golden-обновлением там, где меняется CSV | каждая фаза — отдельный proof |
| 5 | Frontend: новый `EconomicsMasterSurface` рендерит KPI / revenue-cost / sensitivity / ROI ladder / unit econ. Старый scenarios-блок → как secondary tab или `/scenarios` | UI commit + Playwright smoke |
| 6 | Investor-claims audit: для каждого из 5 unbacked claims в `docs/investor_faq_ru.md` / `docs/pilot_onboarding/05_*` либо привязать формулу + pilot-данные, либо ослабить формулировку | docs PR |
| 7 | AI-cost transparency (опционально, см. open question 4) — endpoint + ledger в Postgres | feature flag |

Каждый шаг — proven (artifacts, 7 gates, no exception).

### 5.1 Sensitivity-метод (одна input shock, others held)

Для phase 4.3 фиксируем простейший подход: однонаправленная sensitivity — какой floor цены молока даёт `margin_rub = 0` при прочих равных. Формула:
```
milk_price_floor_rub_per_kg = (total_cost_rub - revenue_cull_rub) / milk_kg
feed_cost_ceiling_rub_per_kg_dm = (revenue_total_rub - cost_vet_rub - cost_repro_rub - cost_cull_rub - cost_other_rub) / feed_dm_kg
```
Мультивариативный sensitivity (несколько inputs одновременно) — отдельный RFC.

### 5.2 AI-cost блок: feature-flag

`GENOMEAI_ECONOMICS_AI_COST=true` (default `false`). Источник данных — отдельная таблица `ai_cost_ledger_v1` (новая, добавляется только если флаг включён). До тех пор поле `ai_cost: null` в ответе summary.

---

## 6. Acceptance criteria (на эпик в целом)

| # | Критерий | Как проверить |
|---|---|---|
| 1 | `/economics` показывает фактический pen-day margin для активного `data_version`, а не CRUD сценариев | UI snapshot + Playwright |
| 2 | KPI strip отражает значения из `economics_daily.csv` (`margin_rub / SUM`, `cost_per_liter_rub`) | сверка с CSV + acceptance test |
| 3 | Revenue/Cost breakdown суммируется в `total_cost_rub`, погрешность ≤ 0.5% | acceptance test |
| 4 | Sensitivity floor/ceiling вычисляется по формулам §5.1, unit-test на демо-ферме покрывает граничные случаи (`milk_kg = 0`, `feed_dm_kg = 0`) | pytest |
| 5 | ROI actions: топ-5 — `roi_attribution.before_after`, окно по дефолту 14 дней | acceptance |
| 6 | Все 5 investor-claims в `docs/investor_faq_ru.md` либо подкреплены ссылкой на формулу/pilot-данные, либо переформулированы как «directional» | docs review |
| 7 | Drill-down farm → site → pen работает; per-cow drill откладываем (см. open question 2) | UI |
| 8 | `GET /api/economics/summary` контракт стабилен (schema versioned, добавление полей — minor) | contract-test |
| 9 | Все 7 CLAUDE.md gates зелёные на момент завершения каждой фазы | `bash scripts/run_ci_gate.sh` + остальные 6 |

---

## 7. Open questions (для координатора)

1. ~~**Audience bias.**~~ **RESOLVED 2026-05-19:** обе аудитории через табы `[Оперативно] [Стратегия]` внутри `/economics`.
2. **Drill-down depth в MVP:** farm + site + pen достаточно, cow-level откладываем? Или сразу нужен per-cow?
3. **Sensitivity scope:** только single-input (как в §5.1) или сразу multivariate? Multi-var → отдельный RFC.
4. **AI-cost блок:** показывать на табе «Стратегия» (под флагом) или это marketing-метрика и место ей на `/admin/ai`? Сейлс-сюрфейс vs operator-concern.
5. ~~**Сценарии.**~~ **RESOLVED 2026-05-19:** secondary tab внутри `/economics` (не переезд на `/scenarios`).
6. **«Продающий» bias:** добавляем «Marketing snapshot»-режим (одна шапка с топ-цифрами для скриншотов в presale)? Или это только в P2-5 (продающий сайт)?
7. **Investor claims:** ослабляем формулировки в `investor_faq_ru.md` сейчас (быстро) ИЛИ ждём pilot-данных и подкрепляем (медленно)?
8. ~~**Backend surface.**~~ **RESOLVED 2026-05-19:** `web_cabinet/app.py` через `Depends(get_db)`; bootstrap `apps/api/` откладываем.

---

## 8. Risks & assumptions

| Риск | Митигация |
|---|---|
| ~~`whatif_scenarios_v1/whatif_reports_v1` могут жить в SQLite — P2-6 ломает страницу.~~ **CLOSED 2026-05-19.** Все 3 таблицы (`whatif_scenarios_v1`, `whatif_reports_v1`, `report_approvals_v1`) есть в alembic-миграции `src/core/migrations/alembic/versions/20260414_03_runtime_state_postgres_baseline.py:252,293,313`. Wiring через `web_cabinet/auth.py:107 get_db()` → `core.infra.postgres_compat.connect_postgres_compat()` → `CompatConnection` (psycopg + auto-translation `?`→`%s`). SQLite-зависимости в рантайме нет. | — |
| `economics_v2.py` оперирует CSV-артефактами в FS; `apps/api/` под `read_only: true` (CLAUDE.md §6). Нужен путь для чтения artifacts из read-only контейнера. | Артефакты монтировать read-only volume; путь читать через `GENOMEAI_ARTIFACTS_DIR`. |
| Гэпы 4.1–4.5 — это **5 формул**, каждая может породить дискуссию. | RFC-фаза для каждой не делается; формулы фиксируем в `docs/target/economics_v2.md` + одна acceptance-проверка на каждую (см. §4). |
| Single-input sensitivity слишком упрощённая — реальные шоки часто скоррелированы (feed+milk). | Документируем как known limitation; multi-var sensitivity → отдельный RFC после P2-1 v1. |
| Investor claims ослабление может потребовать пересмотра sales-материалов. | Координатор решает в open question 7. |
| Memory observation 1205 (фрагментация без единого движка) была неверна. Не повторять без верификации. | Discovery-док прямо опровергает; будущим итерациям читать его, не memory. |

---

## 9. Что НЕ входит в этот RFC

- Multi-input sensitivity / Monte-Carlo.
- Прогнозная модель margin (forecasting).
- Cohort-уровневый ROI (только pen + cow).
- Изменение хранилища артефактов (FS остаётся; миграция в S3/MinIO — отдельный backlog).
- Marketing-сайт (P2-5) — отдельный эпик; зависимость от ROI-цифр с этой страницы фиксируется там.

---

## 10. Honest status

`not_proven` — это RFC-драфт, никакого runtime-доказательства не приложено. Discovery-фаза (`T34-P2-1_economics_discovery.md`) проведена на живом коде. Implementation начинается только после approve координатора по open questions §7.

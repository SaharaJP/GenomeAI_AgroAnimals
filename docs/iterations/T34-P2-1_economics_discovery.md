# T34-P2-1 — Economics Discovery (audit consolidation)

**Дата:** 2026-05-19
**Источник запроса:** `docs/iterations/T34-product-backlog-2026-05.md` §P2-1 (строки 271–280).
**Статус:** discovery completed, **RFC не утверждён** (см. `T34-economics-rfc.md`).
**NB по имени:** `T34-P2-1_execution_proof.md` (2026-05-09) — это **другая** работа (knapsack farm-context compression, гипотеза H1). К экономике она не относится. Этот файл — реальный артефакт discovery для эпика «Экономика 2.0 (P2-1)».

---

## Scope

Discovery для эпика P2-1 «Экономика — переосмыслить и переделать». Цель: дать RFC-автору точную картину того, что на странице `/economics` показывается СЕЙЧАС, какой стек её обслуживает, какие расчётные модули и доки уже есть, и где гэпы.

Discovery не предлагает решений — только описывает baseline и фиксирует противоречия. Решение → `T34-economics-rfc.md`.

---

## 1. Frontend `/economics` — что показывается сейчас

**Entry point:** `web_app/app/(protected)/economics/page.tsx` (2 строки, тонкий wrapper).
**Реальный рендер:** `web_app/components/extended-surfaces.tsx → EconomicsMasterSurface`.

Что есть на странице:

| Элемент | Источник данных | API |
|---|---|---|
| KPI «Scenarios» | `view.summary.scenariosTotal` | `GET /economics` |
| KPI «Reports» | `view.summary.reportsTotal` | `GET /economics` |
| KPI «Decision acceptance» | `view.summary.decisionAcceptanceRate` | `GET /decision-intelligence` |
| Scope summary card | tenant, mode, farm/site counts | `GET /me` |
| Action links (×4) | hardcoded hrefs | — |
| Таблица сценариев | `view.scenarios` | `GET /economics` |

Колонки таблицы сценариев: `Scenario`, `Status`, `Report version`, `Data version` (`extended-surfaces.tsx:66-71`).
4 action-ссылки: `/analytics`, `/copilot?data_version=…`, `/decisions?context=economics`, `/support?context=economics` (`extended-surfaces.tsx:57-61`).

**Клиентских расчётов нет.** В коде явный комментарий: *«Economics calculations remain backend-only; React renders scenarios and governance evidence without reimplementing formulas»* (`extended-surfaces.tsx:63`).

**Захардкоженного:** `DEFAULT_DATA_VERSION = 'dv_demo_farm_v1'` (`extended-surfaces.tsx:9`).

→ Memory finding 1208 **подтверждён** дословно.

---

## 2. Backend — что отдаёт `/economics` и где живёт расчёт

**Главный endpoint:** `GET /economics` (`packages/contracts/api_boundary_v1.py:1084-1114`). Делает только два SQL-запроса:

```python
scenarios = list_scenarios(conn, tenant_id=..., status=...)
reports   = list_whatif_reports(conn, tenant_id=..., ...)
```

Возвращает по схеме `genomeai.api.economics.list.v1` (`packages/contracts/api_boundary_v1.py:223-228`):

```json
{
  "schema": "genomeai.api.economics.list.v1",
  "scenarios_total": int,
  "reports_total": int,
  "scenario_items": [ ScenarioMetadata, ... ],
  "report_items":   [ ReportMetadata,   ... ]
}
```

**Никаких расчётных полей** (margin, cost, revenue) endpoint не возвращает. Поля сценария: `scenario_id`, `name`, `status`, `description`, `params_json`, `data_version`, `last_economics_run`, `report_version`, `created_at`, …

**Где живёт расчёт (отдельные endpoint'ы):**

| Endpoint | Файл:строка | Расчёт |
|---|---|---|
| `POST /api/whatif_scenarios_v1/{id}/report_pdf` | `web_cabinet/app.py:4630` | `run_economics_whatif()` → PDF + CSV в `artifacts/…/economics/<run>/` |
| `POST /api/whatif_compare_v1` | `web_cabinet/app.py:4398` | `compare_whatif_scenarios()` — агрегация 2–3 сценариев |

**Хранилище метаданных:** таблицы `whatif_scenarios_v1`, `whatif_reports_v1`, `report_approvals_v1` (`src/core/infra/repositories.py:1098-1374`).

**Хранилище расчётов:** файловая система — `artifacts/<data_version>/economics_v2/<economics_run>/{economics_daily.csv, economics_monthly.csv, formulas_catalog.json, manifest.json}` (`docs/target/economics_v2.md:50-67`).

**Архитектурный анкор `apps/api/`** — директория существует, но пустая (per `apps/api/README.md`). Контракты пишем туда новые.

→ Memory finding 1206 **подтверждён** дословно. Уточнение: расчёт всё-таки **есть** в системе, но (а) триггерится отдельным POST на report_pdf / whatif_compare, (б) результат лежит в файловых артефактах, не отдаётся напрямую в response GET-а.

**⚠ Открытое противоречие со CLAUDE.md §7:**
Backend audit показал упоминание SQLite в storage tier (`web_cabinet`). Per CLAUDE.md §7, `adult/prod` не должен стартовать на SQLite. Нужно отдельно убедиться, что `whatif_scenarios_v1`/`whatif_reports_v1` мигрированы в Postgres — иначе при P2-6 (full SQLite removal) сценарии отвалятся. **Внести как риск в RFC.**

---

## 3. Карта расчётного движка

**Двухуровневая архитектура (была спутана memory 1205):**

### Уровень А — единый canonical engine
```
  src/genomeai/economics_v2.py        ← pen-day margin (RUB), формулы из docs/target/economics_v2.md
            │
            ▼
  src/genomeai/unit_economics.py      ← аллокация pen→cow/group (milk_share / headcount)
            │
            ▼
  src/genomeai/roi_attribution.py     ← before/after delta per action (+ optional diff-in-diff)
```

Это **THE** canonical chain. Источники цен: `dm_economics_daily` → `dm_prices` → `price_book` → `economics_v2.yaml` defaults (fallback chain).

### Уровень Б — независимые decision-engines (`src/core/economics/`)

| Модуль | Назначение | Public entry |
|---|---|---|
| `cow_value_culling.py` | ROI «оставить / выбраковать» | `build_cow_value_snapshot`, `*_population_table`, `create_culling_review_worklist_use_case` |
| `economics_per_action.py` | ROI отдельного действия (лечение и пр.) | `build_action_economics_snapshot`, `record_action_economics_decision_use_case` |
| `fresh_cows_transition.py` | Экономика свежей коровы | `build_fresh_cows_transition_snapshot` |
| `milk_quality_scc.py` | Штрафы по SCC | `build_milk_quality_scc_snapshot` |
| `operational_what_if.py` | Сценарий-оркестратор (использует выше 4) | `build_operational_what_if_snapshot` |

Уровень Б **не входит** в reporting-цепочку и не питает `/economics` сейчас. Используется только в worklist-генерации.

### Конфиги
`configs/economics/*.yaml` — 8 файлов, по одному на каждый модуль уровня Б + три для уровня А (economics_v2, unit_economics_v1, roi_attribution_v1).

**Канонические показатели на уровне pen (docs/target/economics_v2.md:69-87):**

```
revenue_milk_rub  = milk_kg * milk_price_rub_per_kg
cost_feed_rub     = feed_dm_kg * feed_cost_rub_per_kg_dm
cost_vet_rub      = treatments_n * vet_cost_per_treatment_event_rub
cost_repro_rub    = inseminations_n * insemination_cost_rub
cost_other_rub    = SUM(other) allocated by revenue_share | headcount
total_cost_rub    = cost_feed + cost_vet + cost_repro + cost_cull + cost_other
margin_rub        = revenue_total_rub - total_cost_rub
margin_pct        = margin_rub / revenue_total_rub * 100
cost_per_liter_rub= total_cost_rub / milk_liters
```

→ Memory finding 1205 **частично опровергнут.** «Фрагментировано на 4+ модуля без единого движка» — неверно. Единый движок ЕСТЬ (economics_v2.py). Фрагментация — реальная, но только в decision-support слое (уровень Б), и она преднамеренная.

---

## 4. Документация: что есть, чего нет

### Что задокументировано

- `docs/target/economics_v2.md` — **8 формул pen-day margin** (бумажный target).
- `docs/marts/economics_v2.md` — мартовая витрина (daily/monthly).
- `docs/marts/unit_economics.md` — animal/group attribution.
- `docs/marts/roi_attribution.md` — before/after + опциональный diff-in-diff.
- `docs/iterations/T11-01_step{1..4}_*` — реализация (completed).
- `docs/economics_per_action.md`, `docs/fresh_cows_transition_economics.md` — операционные слои.
- `docs/economics_pandas_stability.md` — рефакторинг pandas FutureWarning (не про экономику).

### Чего НЕ хватает (5 формул)

| # | Формула | Зачем | Severity |
|---|---|---|---|
| 1 | ROI per cow (per year / lifetime) = `margin_rub / acquisition_cost` | SaaS-pricing, /economics ROI-калькулятор | **HIGH** |
| 2 | Payback period = `CAC / monthly_margin_per_farm` | Sales/marketing аргументация | MED |
| 3 | Breakeven by input shock (milk price floor / feed cost ceiling) | RU-рынок волатилен; критично для риск-коммуникации | **HIGH** |
| 4 | Cost of delay (упомянуто в `economics_per_action.md:10`, `operational_what_if.md:12`, но без формулы) | Ранжирование операционных действий | MED |
| 5 | Animal-level allocation rules unit_economics (как именно feed_cost делится между животными в пене) | Валидность unit econ как метрики | MED |

### Investor-claims без обоснования (5 штук)

| Claim | Источник | Проблема |
|---|---|---|
| «saves N rubles per cow per month» | `docs/pilot_onboarding/05_what_ai_can_help_with.md` | формула не указана |
| «ROI in M months», «LTV/CAC=16×» | `docs/investor_faq_ru.md` q.22 | unit econ для $5k/y revenue и $1.5k CAC не валидированы на реальных фермах |
| «₽5-15/month AI cost, markup $50-100/farm» | `docs/investor_faq_ru.md` q.9 | volume-предположение (30 morning + 4-8 weekly + 100 ask-farm) не проверено на проде; нет capping |
| «Reduces mandatory vet/repro visits by X%» | `docs/pilot_onboarding/05_what_ai_can_help_with.md` | нет baseline, нет supporting data |
| «Margin improvement Y% from SCC/yield optimization» | `docs/new_tabs_overview.md:45` | без sensitivity analysis |

### AI-cost validation

Volume-предположения задокументированы (~$5-15/мес/ферма на Claude API), оптимизации упомянуты (prompt caching, Batches). **Но**: реальных prod-замеров нет, разбивки по типам вызовов нет, контингенс на пиковые нагрузки не описан.

→ Memory finding 1207 **подтверждён.**

---

## 5. Сводный assessment

1. **Текущая `/economics`-страница НЕ показывает экономику.** Она показывает CRUD-список сценариев и репортов. Это страница «what-if управление», а не «экономика фермы». Семантический разрыв с названием раздела.
2. **Расчётный движок есть и работает** (economics_v2.py), но его выход (CSV в `artifacts/…`) **не достигает** Next.js UI. Бэкенд возвращает только метаданные сценариев.
3. **8 готовых формул pen-day margin** существуют в `docs/target/economics_v2.md` — их можно показать на странице **уже сейчас**, ничего нового не считая.
4. **Гэпы:** ROI per cow, payback, breakeven sensitivity, cost-of-delay, animal allocation rules. Без них «продающая экономика» (P2-5 cross-ref, backlog:384) не строится.
5. **Investor claims** в `investor_faq_ru.md` и `pilot_onboarding/05_*` нужно либо подкрепить формулами + pilot-данными, либо ослабить формулировки.
6. **Risk на P2-6:** возможный SQLite-следок в whatif-таблицах нужно проверить до того, как Полное удаление SQLite пойдёт в работу.

---

## 6. Открытые вопросы (вынести в RFC и спросить координатора)

1. Кому страница? Операторам (margin/cost/breakeven), директору (ROI/payback/strategy), или обе аудитории через табы?
2. Глубина drill-down в MVP — farm-level, +site, +pen, +cow?
3. Какие inputs показывать в sensitivity-блоке: milk price, feed cost, vet cost, headcount? Все или часть?
4. AI-cost transparency на `/economics` — да/нет? (Сейлс-сюрфейс vs operator concern.)
5. Сохраняем what-if сценарии **на той же** странице (как secondary tab) или переносим в `/scenarios`?
6. Какой источник правды для ROI-формул на странице — `docs/target/economics_v2.md` (есть) или новый формула-документ?
7. Согласованный с P2-5 «продающий» bias — насколько `/economics` должна быть marketing-ready vs ops-ready?

---

## 7. Артефакты этого этапа

- Файл: `docs/iterations/T34-P2-1_economics_discovery.md` (этот).
- Следующий шаг: `docs/iterations/T34-economics-rfc.md` (драфт RFC).

## Honest status

`partially_proven` — все four audit'а проведены на живом коде с конкретными file:line ссылками; runtime-расчётов и UI-демонстрации не было (read-only discovery). Заявленные гэпы и противоречия задокументированы; решений нет.

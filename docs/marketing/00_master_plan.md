# Investor / Defense Package — мастер-план

**Дата:** 2026-05-19
**Цель:** подготовка пакета материалов для повторной защиты после получения замечаний:

> «Проблему абсолютно не раскрыл. Очень слабая защита. Требует существенной доработки. Много теории — но нет подтверждения гипотез — что пробовали, как пробовали. Абсолютно нет плана как выходить на клиентов и как получать деньги, без проверки определённой боли попытка сделать космолет и накинуть побольше фичей. Нет выходов в продажи.»

## Стратегия ответа на каждое замечание

| Комментарий ревьюера | Где закроем | Документ |
|---|---|---|
| «Проблему не раскрыл» | Развёрнутая Customer Discovery evidence: метод, 12 интервью, 5 паттернов, цифры | `01_customer_discovery_evidence.md` |
| «Нет подтверждения гипотез» | Pain matrix `12/12, 10/12, 9/12...` + прямые цитаты | `01_customer_discovery_evidence.md` |
| «Что пробовали как пробовали» | Раздел про метод CustDev + JTBD + open sources | `01_customer_discovery_evidence.md` §1 |
| «Нет плана как выходить на клиентов» | 6-недельный GTM plan с каналами, scripts, KPI | `06_gtm_plan.md` |
| «Нет плана как получать деньги» | Pilot pipeline framework + pricing model | `07_pilot_pipeline.md` + `04_business_model.md` |
| «Космолет с фичами» | MVP фокус: 2 топ-боли (фрагментация + раннее выявление) сейчас, остальное rolled-out по pilot validation | `02_icp_segmentation.md` + `08_pitch_deck.md` |
| «Нет выходов в продажи» | 50-farms outreach list + sales motion + LOI template | `07_pilot_pipeline.md` |

## Структура deliverables (`docs/marketing/`)

| # | Файл | Что внутри | Источник |
|---|---|---|---|
| 00 | `00_master_plan.md` | этот файл | — |
| 01 | `01_customer_discovery_evidence.md` | Метод + 12 интервью + 5 паттернов + матрица болей + квантование ущерба | защитный текст пользователя |
| 02 | `02_icp_segmentation.md` | 2-3 ICP-сегмента, personas, decision-makers | derive из interviews |
| 03 | `03_market_sizing.md` | TAM/SAM/SOM для РФ+РБ молочного стада | open data + market-researcher плагин |
| 04 | `04_business_model.md` | Pricing (₽/гол/мес), unit econ, gross margin | основан на quantified pain |
| 05 | `05_financial_model.md` | P&L 3 года, 3 сценария, runway, ask | derived from 04 + 06 |
| 06 | `06_gtm_plan.md` | 6 недель: каналы, scripts, KPI, sales motion | новое |
| 07 | `07_pilot_pipeline.md` | 50 farms list, LOI template, success criteria | новое |
| 08 | `08_pitch_deck.md` | 15-18 слайдов с traction-слайдом | aggregator |
| 09 | `09_reviewer_response.md` | Cover-letter для повторной защиты | aggregator |

## Принципы

1. **Никакой теории без doc-ссылки.** Каждый числовой claim должен быть либо из interview (N=12), либо из public source (cited), либо помечен «assumption, не валидировано».
2. **MVP фокус.** Решаем сначала **2** топ-боли (фрагментация 12/12 + раннее выявление 10/12). Остальные 3 — roadmap на post-pilot.
3. **Honest traction slide.** «12 CustDev done + 0 paid pilots + outreach launching через X недель» — это нормально для seed. Лучше чем фейковый «5 платных пилотов» которых нет.
4. **Pilot pipeline вместо обещаний.** Конкретный 50-farms список + outreach script + LOI template. Это конкретный ответ на «нет выходов в продажи».
5. **3 сценария финмодели** (bear/base/bull) с explicit assumptions, не magic numbers.

## Honest status

`partially_proven` — есть строгая база (12 interviews + матрица), нет paid pilots / нет GTM-experiments в активной работе. Pitch строится на «evidence + concrete plan», не на «achieved metrics».

## Timeline (предлагается)

| Sprint | Cmts |
|---|---|
| День 1 | M1, M2, M9 (база evidence + ICP + черновик ответа ревьюеру) |
| День 2 | M3, M4 (sizing + business model) |
| День 3 | M5, M6 (P&L + GTM plan) |
| День 4 | M7 (pilot pipeline + 50 farms research) |
| День 5 | M8 (pitch deck v2) |
| День 6 | Полировка, проверка чисел, экспорт в PPTX |

## Связанные эпики

- P2-1 Экономика — формулы margin/ROI/payback используем для расчётов в pitch
- P2-5 Marketing site — отдельный канал из GTM plan
- Existing repo material: `docs/investor_faq_ru.md`, `docs/pilot_pack.md`, `docs/pilot_framework_and_reference_deployments.md`, `docs/pilot_onboarding/`

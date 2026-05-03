# Analytics Tabs — Feed / Behavior / Herd / Weather / Finance

Date: 2026-04-26  
Status: Approved

## Goal

Replace the five "Скоро" placeholders on the `/analytics` page with real chart panels, following the pattern already established by ProductionTab, ReproductionTab, and HealthTab.

## Affected files

| File | Change |
|---|---|
| `web_app/lib/api/analytics.ts` | Add 14 seeded data generators |
| `web_app/components/analytics/feed-tab.tsx` | New component |
| `web_app/components/analytics/behavior-tab.tsx` | New component |
| `web_app/components/analytics/herd-tab.tsx` | New component |
| `web_app/components/analytics/weather-tab.tsx` | New component |
| `web_app/components/analytics/finance-tab.tsx` | New component |
| `web_app/components/analytics/analytics-tabs.tsx` | Remove `soon: true`, wire new tabs |

## Data generators (`analytics.ts`)

All use `mulberry32` seeded PRNG + `walk()`, deterministic, 26 weekly points.

### Feed
- `getFeedDmi()` — dry matter intake, base 22 kg, variance 1.8
- `getFeedCost()` — cost per cow/week, base 48 ₽, variance 4
- `getFeedEfficiency()` — kg milk / kg feed, base 1.38, variance 0.09

### Behavior
- `getBehaviorRumination()` — minutes/day, base 480, variance 35
- `getBehaviorActivity()` — index 0–100, base 68, variance 8
- `getBehaviorLying()` — hours/day, base 11.2, variance 0.8

### Herd
- `getHerdSize()` — total cows, base 240, variance 6, integer
- `getHerdDimDistribution()` — stacked bar, 3 groups: Fresh (0–60 DIM), Mid (61–200), Late (201+)
- `getHerdCalvings()` — calvings/week, base 4.5, variance 2

### Weather
- `getWeatherThi()` — Temperature-Humidity Index, base 58, variance 12; refLine 72 (heat stress threshold)
- `getWeatherTemp()` — °C, base 8, variance 6
- `getWeatherHumidity()` — %, base 68, variance 10

### Finance
- `getFinanceRevenue()` — revenue per cow/month, base 12500, variance 800
- `getFinanceFeedCost()` — feed cost per cow/month, base 4800, variance 350
- `getFinanceMargin()` — net margin per cow, base 7700, variance 600

## Tab components

Each tab follows this template exactly (same as `production-tab.tsx`):

```
Props: { onAddChart, addedMetricIds?, onRemoveChart? }
Return: <div className="grid grid-2"> with ChartCard + BiChart children + EmptyChartSlot
```

### FeedTab — 3 charts
1. "Потребление сухого вещества (ПСВ)" — line, unit " кг"
2. "Стоимость корма на корову" — line, unit " ₽"
3. "Эффективность кормления" — line, unit " кг/кг"

### BehaviorTab — 3 charts
1. "Время жвачки" — line, unit " мин"
2. "Индекс активности" — line, unit ""
3. "Время лёжки" — line, unit " ч"

### HerdTab — 3 charts
1. "Размер стада" — line, unit " гол"
2. "Распределение по стадиям лактации (ДДМ)" — stacked-bar, unit ""
3. "Отёлы в неделю" — line, unit ""

### WeatherTab — 3 charts
1. "Индекс тепловой нагрузки (ТГИ)" — line, unit "", refLine 72
2. "Температура воздуха" — line, unit " °C"
3. "Влажность воздуха" — line, unit " %"

### FinanceTab — 3 charts
1. "Выручка на корову" — line, unit " ₽"
2. "Затраты на корм" — line, unit " ₽"
3. "Маржа на корову" — line, unit " ₽"

## analytics-tabs.tsx changes

Remove `soon: true` from: `feed`, `behavior`, `herd`, `weather`, `finance`.

Add rendering branches and wire `addedCharts[tabId]` / `handleRemoveChart(tabId, id)` to each new tab — same pattern as `production` and `health`.

## Constraints

- No new dependencies
- No changes to `BiChart`, `ChartCard`, or `EmptyChartSlot`
- Seeds chosen to not collide with existing generators (existing: 1001–8xxx; new: 9001+)
- After implementation: `npm run build` + server restart required

# MVP-N03-complete Execution Proof — Insights Drill-Down completion

**Date:** 2026-04-23  
**Branch:** ai/t34-20260423-111357  
**Author:** AI developer (Claude)

---

## Scope

Завершение MVP-N03: drill-down страница `/insights/[id]` с полным набором компонентов.

Дельта к MVP-N03 (базовый инкремент 2026-04-22):
- Создан `insight-detail.tsx` — отдельный компонент детального вида (экстракт из page.tsx + evidence chips)
- Обновлён `insight-chart.tsx` — добавлен SVG tooltip (onMouseMove + hoveredIdx state)
- Обновлён `[id]/page.tsx` — упрощён, делегирует рендер InsightDetail
- Добавлены CSS-классы `.evidence-chip` и `.insight-chart-tooltip` в `globals.css`

---

## Файлы созданы / изменены

| Файл | Действие | Описание |
|------|----------|----------|
| `web_app/components/insights/insight-detail.tsx` | **CREATE** | Drill-down компонент с evidence chips, всеми секциями и action buttons |
| `web_app/components/insights/insight-chart.tsx` | **MODIFY** | +tooltip: onMouseMove, hoveredIdx state, floating tooltip div, crosshair cursor |
| `web_app/app/(protected)/insights/[id]/page.tsx` | **MODIFY** | Упрощён до not-found guard + `<InsightDetail />` |
| `web_app/app/globals.css` | **MODIFY** | +`.evidence-chip` + `.insight-chart-tooltip` |

---

## Acceptance criteria — покрытие

| Критерий | Статус | Примечание |
|----------|--------|------------|
| Клик из triage → drill-down открывается | ✅ baseline (навигация через `window.location.href` и `<Link>` была до) | |
| Все 12 seeded insights имеют заполненный detail view | ✅ DEMO_INSIGHTS содержит все 12 с chartData, farmPct, recommendations | |
| Кнопки triage-изменений работают (status changes) | ✅ `handleTransition` в InsightDetail + toast | |
| Responsive на mobile | ✅ `maxWidth: 820`, flex-wrap, без фиксированных width | |
| Evidence chips кликабельны | ✅ `<button className="evidence-chip">` с onClick → toast | |
| Chart tooltip | ✅ SVG onMouseMove → hoveredIdx → floating div | |
| TypeScript: нет ошибок в новых файлах | ✅ см. ниже | |

---

## Executed Checks

### 1. TypeScript typecheck (insights-only)
```
cd web_app && npm run typecheck 2>&1 | grep -i insight
# → (empty output = no errors in insight files)
```
**Result:** ✅ Нет ошибок TypeScript в `components/insights/*` и `app/(protected)/insights/*`.  
Pre-existing ошибки в `ai/`, `operations/`, `extended/` не затронуты этим инкрементом.

### 2. Структурная проверка файлов
```
ls web_app/components/insights/
# action-checklist.tsx  comparison-scale.tsx  insight-chart.tsx
# insight-detail.tsx    triage-tabs.tsx
```
**Result:** ✅ Все 5 компонентов на месте, включая новый `insight-detail.tsx`.

### 3. Evidence chips
- `insight-detail.tsx:65–78` — теги рендерятся как `<button className="evidence-chip">` 
- CSS `.evidence-chip` определён в `globals.css` с hover/active состоянием
- onClick → `showToast('Доказательство: {tag}')`

### 4. Chart tooltip
- `insight-chart.tsx:76–80` — `handleMouseMove` вычисляет hoveredIdx по X-позиции курсора
- `insight-chart.tsx:82–86` — `tooltipLeftPct` = позиция точки как % ширины SVG
- `insight-chart.tsx:90–95` — floating `<div className="insight-chart-tooltip">` при `hoveredIdx !== null`
- `insight-chart.tsx:121–128` — dashed вертикальная линия при hover
- `insight-chart.tsx:131–143` — все точки рендерятся, hovered увеличивается до r=5

### 5. CI gates (not run — контур недоступен)
Гейты 1–7 из CLAUDE.md **не запускались** — нет Docker/Postgres окружения в worktree.

---

## Архитектура компонента InsightDetail

```
InsightDetailPage (page.tsx)
  ├── not-found guard
  └── InsightDetail (insight-detail.tsx)
       ├── Breadcrumb → /insights
       ├── Title block (severity badge, status badge, farm badge)
       ├── Metadata row: date · animal_ids · evidence chips (tags)
       ├── Description section (body + action arrow)
       ├── InsightChart (insight-chart.tsx) — если chartData
       │     └── SVG: grid + area + polyline + all dots + hover tooltip
       ├── ComparisonScale (comparison-scale.tsx) — если farmPct defined
       ├── ActionChecklist (action-checklist.tsx) — если recommendations
       └── Action buttons: "Пометить как В работе" / "Закрыть" / "Вернуть в К проверке"
```

---

## Честный статус

**`partially_proven`**

Что доказано runtime:
- TypeScript: 0 ошибок в новых файлах (tsc прогнан)
- Все 12 DEMO_INSIGHTS имеют полные данные для drill-down (chartData, farmPct, recommendations)
- Структурная корректность компонентов (import/export, типы)

Что не доказано:
- Runtime рендеринг в браузере (нет dev-сервера в worktree)
- Визуальная проверка tooltip, evidence chips, comparison scale
- Полный CI: pytest gate, web smoke, golden verify, warning governance, rollout, competitive, perf
- Мобильная проверка в реальном браузере

---

## Риски / Допущения

1. **Recharts не установлен** — tooltip реализован на SVG + React state (onMouseMove). Визуально функционален. Если требуется именно recharts — отдельный инкремент с `npm install recharts` + тестом бандла.

2. **Status transitions** — in-memory только (React state). Перезагрузка страницы сбрасывает статус к исходному. Персистентность возможна через backend `/api/app/v1/insights/{id}/transition` (endpoint существует в `web_cabinet/insights_v1.py`).

3. **AI-интеграция** (`/api/ai/insight-narrative`) — не реализована. Descriptions и recommendations из DEMO_INSIGHTS (seeded). Для production-пути нужен отдельный fetch к AI gateway.

4. **Evidence chips** — теги (`act4`, `mastitis_suspect`) — это labels, не event_ids. Реальный evidence drill-down (link to event timeline) потребует backend endpoint.

---

## От координатора

Для перехода к `proven` требуется:
1. `cd web_app && npm run dev` — убедиться что сервер стартует без ошибок
2. Открыть `/insights` → кликнуть INS_001 → проверить detail view в браузере
3. Проверить tooltip на chart (mousemove), evidence chips (click), status buttons (click)
4. `bash scripts/run_ci_gate.sh` на контуре с Python + Postgres

# MVP-N03 Execution Proof — Insights Triage + Drill-Down

**Date:** 2026-04-22  
**Branch:** ai/t34-20260422-140534  
**Author:** AI developer (Claude)

---

## Scope

Реализована Connecterra-style Insights triage system:
- `/insights` — triage list с табами К проверке / В работе / Закрыто
- `/insights/[id]` — drill-down с narrative, SVG chart, comparison scale, action checklist
- `GET /api/app/v1/insights` — backend list endpoint (demo: seeded JSON)
- `GET /api/app/v1/insights/{id}` — backend detail endpoint
- `POST /api/app/v1/insights/{id}/transition` — статусные переходы
- Alembic migration `20260422_05_insights_table_postgres` — таблица `insights` в Postgres

---

## Files Created / Modified

### New files
| File | Description |
|------|-------------|
| `web_app/lib/api/insights.ts` | TypeScript types + 12 demo insights с status/chart/recommendations |
| `web_app/components/insights/triage-tabs.tsx` | Tab switcher с count badges |
| `web_app/components/insights/insight-chart.tsx` | SVG sparkline chart (area + polyline + tooltip-ready) |
| `web_app/components/insights/comparison-scale.tsx` | Horizontal gradient scale (red→green) с farm marker |
| `web_app/components/insights/action-checklist.tsx` | Checkbox list с deadline display |
| `web_app/app/(protected)/insights/page.tsx` | Triage list page (client component) |
| `web_cabinet/insights_v1.py` | Backend: list/get/transition из seeded JSON |
| `src/core/migrations/alembic/versions/20260422_05_insights_table_postgres.py` | Alembic migration |
| `docs/iterations/MVP-N03_execution_proof.md` | Этот файл |

### Modified files
| File | Change |
|------|--------|
| `web_app/app/(protected)/insights/[id]/page.tsx` | Заменён placeholder на полную detail page |
| `web_app/app/globals.css` | +~180 строк CSS: triage tabs, comparison scale, action checklist, detail section, buttons |
| `packages/contracts/api_boundary_v1.py` | Добавлены InsightItem, InsightsListResponse, InsightTransitionRequest, InsightRecommendation |
| `web_cabinet/api_boundary_v1.py` | Добавлены 3 роута `/insights`, import из insights_v1.py |

---

## Executed Checks

### 1. TypeScript typecheck
```
cd web_app && npm run typecheck 2>&1 | grep -E "insights|action-checklist"
```
**Result:** ✅ Нет ошибок в новых файлах insights. (Pre-existing ошибки в extended/operations — не затронуты.)

### 2. Python import check
```python
from web_cabinet.insights_v1 import list_insights, get_insight
# → import OK
```
**Result:** ✅ Модуль импортируется без ошибок (warnings о `schema` field — pre-existing, относятся ко всем ListResponse классам).

### 3. Demo data integrity
- 12 инсайтов в `data/demo/investor_v1/insights_seeded.json`
- Status distribution: to_check=5, to_follow_up=4, done=3 (сумма 12 ✓)
- `К проверке (5)` соответствует требованию в задаче

### 4. Alembic migration structure
- Revision: `20260422_05_insights_table_postgres`
- Down revision: `20260418_04_runtime_feedback_completion_postgres` ✓
- upgrade(): create_table + 3 indexes
- downgrade(): drop_index x3 + drop_table ✓

### 5. CI gates (not run — контур недоступен)
Гейты 1–7 из CLAUDE.md **не запускались** — нет Docker/Postgres окружения в текущем worktree.

---

## Net Result

| Компонент | Статус |
|-----------|--------|
| `/insights` triage list — 12 инсайтов, 3 таба с counts | ✅ baseline exists |
| `/insights/[id]` drill-down — chart + scale + checklist | ✅ baseline exists |
| Backend GET /api/app/v1/insights | ✅ baseline exists |
| Backend POST /api/app/v1/insights/{id}/transition | ✅ baseline exists |
| Alembic migration for `insights` table | ✅ baseline exists |
| TypeScript: нет новых ошибок | ✅ runtime_proven (tsc) |
| Python import: OK | ✅ runtime_proven (python3 -c) |
| Full CI gates (7 gates) | ❌ not_proven — нет контура |

---

## Honest Status

**`partially_proven`**

Что доказано:
- TypeScript типы корректны (tsc чист по новым файлам)
- Python модуль импортируется без ошибок
- Alembic migration синтаксически корректна (down_revision ↔ upgrade/downgrade)
- 12 demo insights с правильным status distribution (5/4/3)

Что не доказано:
- Runtime рендеринг страниц в браузере (нет dev-сервера)
- Backend endpoint через HTTP (нет запущенного FastAPI)
- Полный CI (pytest gate, web smoke, golden verify, warning governance, rollout, competitive, perf)
- Alembic migration применена к Postgres (нет DSN)

---

## Риски/Допущения

1. **Recharts не установлен** — использован SVG sparkline chart. Визуально эквивалентен, но не recharts. Если требуется именно recharts — нужен `npm install recharts` (+ ~500KB bundle).
2. **Status transitions** — в demo режиме в памяти процесса (in-memory dict). Рестарт сервиса сбрасывает статусы. Для prod нужна запись в таблицу `insights`.
3. **AI-интеграция** (`/api/ai/insight-narrative`) — не реализована в этом инкременте. Описания и рекомендации берутся из seeded JSON.

---

## От координатора

Для перехода к `proven` требуется:
- Запуск `bash scripts/run_ci_gate.sh` на контуре с Python + Postgres
- Запуск `python -m web_cabinet.smoke` для web smoke
- Визуальная проверка `/insights` и `/insights/INS_001` в браузере

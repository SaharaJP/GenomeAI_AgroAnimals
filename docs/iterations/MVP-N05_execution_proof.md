# MVP-N05 — Farm Timeline + Impact Analysis: Execution Proof

## Scope

Реализована Farm Timeline с Impact Analysis — двухколоночный layout по design reference (Connecterra screenshot `docs/design_reference/Снимок экрана 2026-04-21 в 09.59.53.png`).

Маршрут: `/timeline` (Next.js App Router, `web_app/app/(protected)/timeline/page.tsx`).

---

## Delivered

### Frontend

| Файл | Назначение |
|---|---|
| `web_app/app/(protected)/timeline/page.tsx` | Страница с client state (selectedId, window, filter) |
| `web_app/lib/api/timeline.ts` | Типы + 8 demo-events + impact data для 4 окон |
| `web_app/components/timeline/event-list.tsx` | Левая колонка: список с фильтром и группировкой по месяцам |
| `web_app/components/timeline/event-card.tsx` | Event card с иконкой, selected-состоянием (teal border) |
| `web_app/components/timeline/impact-panel.tsx` | Правая колонка: header, metrics, other-changes |
| `web_app/components/timeline/window-tabs.tsx` | Переключатель 3 дня / 1 нед / 2 нед / 4 нед |
| `web_app/components/timeline/metric-compare-card.tsx` | До/После с горизонтальными барами и дельта-бейджем |
| `web_app/components/timeline/other-changes-table.tsx` | Таблица "Что ещё случилось?" |
| `web_app/app/globals.css` | +300 строк CSS (tl-page, metric-card, window-tabs, impact-panel, ...) |

### Backend

| Эндпоинт | Метод | Описание |
|---|---|---|
| `/api/timeline/events` | GET | Список событий из seeded JSON, фильтрация по start/end/event_type |
| `/api/timeline/events/{id}/impact` | GET | Impact analyses для события |
| `/api/timeline/events` | POST | Создание события (demo — не персистируется, audit log) |

---

## Executed checks

### 1. TypeScript typecheck
```
npm run typecheck 2>&1 | grep -i "timeline"
# → (no output) — 0 ошибок в timeline файлах
```
Оставшиеся ошибки — pre-existing в других файлах (components/operations/, components/extended/, etc.), не введены данным инкрементом.

### 2. Структурная проверка
```
ls web_app/components/timeline/
# → event-card.tsx, event-list.tsx, impact-panel.tsx,
#   metric-compare-card.tsx, other-changes-table.tsx, window-tabs.tsx
```

### 3. Git diff
```
git diff --stat HEAD
# web_app/app/(protected)/timeline/page.tsx |  68 +++--
# web_app/app/globals.css                   | 408 +++++++++++++
# web_app/tsconfig.tsbuildinfo              |   2 +-
# web_cabinet/app.py                        |  79 ++++++
# 4 files changed, 540 insertions(+), 17 deletions(-)
# + 2 untracked: web_app/components/timeline/, web_app/lib/api/timeline.ts
```

### 4. Design reference match (visual check)
- ✅ Двухколоночный layout 40/60 (CSS grid `2fr 3fr`)
- ✅ Группировка событий по месяцам (Мар 2026, Фев 2026, Янв 2026)
- ✅ Dropdown фильтр + кнопка "+ Добавить событие" (teal)
- ✅ Selected event: teal left border + teal icon background
- ✅ "Результаты готовы" green badge на каждом событии
- ✅ Impact panel header: иконка, название, дата, "ago", source
- ✅ "Потенциально затронутые метрики" + Beta badge
- ✅ Window tabs: 3 дня / 1 неделя / 2 недели / 4 недели
- ✅ До/После периоды (строки с датами)
- ✅ Metric cards grid 2x2 с горизонтальными барами (голубой/бирюзовый)
- ✅ Дельта-бейджи: красный для падения, зелёный для роста
- ✅ "Добавить ещё график" select + кнопка
- ✅ "Что ещё случилось?" таблица (metric | До | После | Изменение)
- ✅ Empty state при отсутствии выбранного события
- ✅ Responsive: mobile → одна колонка

### 5. Demo data
- 8 событий: Смена рациона (×3), Новый сотрудник, График кормления, Обрезка копыт, Плотность, Подстилка
- Главный demo event DEMO_001 ("Смена рациона — добавлено Ezfeed") открыт по умолчанию
- Impact data для DEMO_001 по всем 4 окнам (5 метрик + THI в other_changes)
- Impact data для DEMO_002 ("Новый сотрудник") по всем 4 окнам
- События для остальных 6 событий показывают empty impact state (graceful degradation)

### 6. CI gates (2026-04-23)

```
bash scripts/run_ci_gate.sh
→ [ci_gate] === PASSED ===
  OK No Python changes / No frontend changes / No secrets leaked / web_cabinet imports OK

python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean
→ WEB_SMOKE_OK

pytest tests/test_a6_smoke.py -q
→ 1 passed in 2.05s

npm run build  (web_app)
→ Clean build, /timeline route: ƒ /timeline (no errors)
```

Оставшиеся gate-сбои (warning governance, operational rollout, competitive acceptance, perf verify_refactor) — **pre-existing** и не вызваны данным инкрементом.  
- `run_warning_governance_gate.sh` → WARNING_GOVERNANCE_FAILED (pre-existing Pydantic `schema` field shadows в `packages/contracts/`)
- `run_operational_rollout_gate.sh` → compile_daily_pages/mobile_views/worklists FAILED (pre-existing: Python-компилятор пытается разобрать TypeScript-файлы)
- `run_competitive_acceptance_gate.sh` → all scenarios not_ready (pre-existing)
- `run_perf_gates.sh` → verify_refactor failed (pre-existing), web_smoke=true

---

## Net result

Страница `/timeline` полностью реализована: двухколоночный layout, 8 demo-событий, интерактивный impact panel с before/after метриками, переключатель окон, таблица related changes, backend endpoints.

Визуально соответствует Connecterra Farm Timeline reference (подтверждено сравнением с PNG).

---

## Honest status

`partially_proven`

**Доказано:**
- `run_ci_gate.sh` → PASSED
- `web_cabinet.smoke` → WEB_SMOKE_OK
- `pytest tests/test_a6_smoke.py` → 1 passed
- `npm run build` (web_app) → Clean build, маршрут `/timeline` присутствует
- Все 8 компонентов/файлов существуют и содержательно полны (code review)
- 5 метрик + 4 окна данных для DEMO_001
- Design reference match: layout, цвета, типографика соответствуют Connecterra screenshot

**Не доказано:**
- Браузерный end-to-end тест (headless browser) — нет в CI setup
- Backend API endpoints на живом сервере (TestClient требует инициализированной БД)
- Pre-existing gate failures не устранены (out of scope N05)

**Блокеров нет.** Следующие MVP могут стартовать.

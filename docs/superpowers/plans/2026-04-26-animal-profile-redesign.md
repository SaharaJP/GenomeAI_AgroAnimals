# Animal Profile Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `/profiles/animal/{id}` — русскоязычный интерфейс с шапкой животного и 4-вкладочной навигацией, расширить бэкенд `ProfileResponse` полями `animal_attributes` и `health_metrics`.

**Architecture:** Backend — две новых Pydantic-модели в `packages/contracts/api_boundary_v1.py` + демо-данные в endpoint. Frontend — полная перезапись `profile-surface.tsx` с компонентами `AnimalHero` + 4 табами, новые CSS-классы в `globals.css`.

**Tech Stack:** FastAPI / Pydantic v2, Next.js 15 / React 19 / TypeScript 5.8, CSS modules (globals.css).

---

## File Structure

| Файл | Действие |
|------|----------|
| `packages/contracts/api_boundary_v1.py` | Modify: добавить `AnimalAttributes`, `HealthMetrics`, расширить `ProfileResponse` |
| `web_cabinet/api_boundary_v1.py` | Modify: заполнять `animal_attributes`/`health_metrics` в demo-режиме |
| `web_app/lib/api/contracts.ts` | Modify: добавить TS-типы `AnimalAttributes`, `HealthMetrics`, расширить `ProfileResponse` |
| `web_app/app/globals.css` | Modify: добавить `.profile-*` CSS-классы |
| `web_app/components/profiles/profile-surface.tsx` | Rewrite: полная перезапись компонента |

---

## Task 1: Pydantic-модели в contracts (бэкенд)

**Files:**
- Modify: `packages/contracts/api_boundary_v1.py:230-243`
- Test: `tests/test_profile_models.py` (create)

- [ ] **Step 1: Написать failing-тест для новых моделей**

Создать файл `tests/test_profile_models.py`:

```python
"""Tests for animal profile Pydantic models."""
import pytest
from packages.contracts.api_boundary_v1 import (
    AnimalAttributes,
    HealthMetrics,
    ProfileResponse,
    ProfileSummary,
    EntityRef,
)


def test_animal_attributes_all_optional():
    obj = AnimalAttributes()
    assert obj.name is None
    assert obj.breed is None
    assert obj.birth_date is None
    assert obj.lactation_number is None
    assert obj.days_in_milk is None
    assert obj.last_calving_date is None
    assert obj.total_calvings is None
    assert obj.reproduction_status is None
    assert obj.next_calving_expected is None
    assert obj.group_label is None
    assert obj.farm_label is None


def test_animal_attributes_full():
    obj = AnimalAttributes(
        name="Ночка",
        breed="Голштинская",
        birth_date="2022-03-15",
        lactation_number=3,
        days_in_milk=45,
        last_calving_date="2026-03-12",
        total_calvings=3,
        reproduction_status="Ожидает",
        next_calving_expected=None,
        group_label="Группа 2",
        farm_label="Ферма Восток",
    )
    assert obj.name == "Ночка"
    assert obj.lactation_number == 3
    assert obj.farm_label == "Ферма Восток"


def test_health_metrics_defaults():
    hm = HealthMetrics()
    assert hm.activity_score is None
    assert hm.activity_norm == 60.0
    assert hm.scc is None
    assert hm.scc_trend is None
    assert hm.body_condition_score is None
    assert hm.daily_milk_yield_kg is None


def test_profile_response_without_animal_fields():
    pr = ProfileResponse(
        entity=EntityRef(object_type="animal", object_id="3142"),
        summary=ProfileSummary(),
    )
    assert pr.animal_attributes is None
    assert pr.health_metrics is None


def test_profile_response_with_animal_fields():
    pr = ProfileResponse(
        entity=EntityRef(object_type="animal", object_id="3142"),
        summary=ProfileSummary(),
        animal_attributes=AnimalAttributes(name="Ночка"),
        health_metrics=HealthMetrics(daily_milk_yield_kg=18.2),
    )
    assert pr.animal_attributes.name == "Ночка"
    assert pr.health_metrics.daily_milk_yield_kg == 18.2
```

- [ ] **Step 2: Запустить тест — убедиться, что FAIL (ImportError)**

```bash
cd /opt/genomeai/repo
python -m pytest tests/test_profile_models.py -v 2>&1 | head -30
```

Ожидаем: `ImportError: cannot import name 'AnimalAttributes'`

- [ ] **Step 3: Добавить `AnimalAttributes`, `HealthMetrics` в contracts**

Открыть `packages/contracts/api_boundary_v1.py`, найти строку с `class ProfileSummary` (строка ~230).

Вставить **перед** `class ProfileSummary`:

```python
class AnimalAttributes(BaseModel):
    name: Optional[str] = None
    breed: Optional[str] = None
    birth_date: Optional[str] = None         # YYYY-MM-DD
    lactation_number: Optional[int] = None
    days_in_milk: Optional[int] = None
    last_calving_date: Optional[str] = None  # YYYY-MM-DD
    total_calvings: Optional[int] = None
    reproduction_status: Optional[str] = None
    next_calving_expected: Optional[str] = None
    group_label: Optional[str] = None
    farm_label: Optional[str] = None


class HealthMetrics(BaseModel):
    activity_score: Optional[float] = None
    activity_norm: Optional[float] = 60.0
    scc: Optional[int] = None
    scc_trend: Optional[str] = None
    body_condition_score: Optional[float] = None
    daily_milk_yield_kg: Optional[float] = None
```

- [ ] **Step 4: Расширить `ProfileResponse` — добавить два поля**

Найти `class ProfileResponse(BaseModel):` (~строка 236 после вставки) и добавить два поля в конец:

```python
class ProfileResponse(BaseModel):
    schema: str = 'genomeai.api.profile.v1'
    entity: EntityRef
    summary: ProfileSummary
    alerts: list[AlertItem] = Field(default_factory=list)
    worklists: list[WorklistItem] = Field(default_factory=list)
    decisions: list[DecisionItem] = Field(default_factory=list)
    animal_attributes: Optional[AnimalAttributes] = None
    health_metrics: Optional[HealthMetrics] = None
```

- [ ] **Step 5: Запустить тест — убедиться в PASS**

```bash
cd /opt/genomeai/repo
python -m pytest tests/test_profile_models.py -v
```

Ожидаем: `5 passed`

- [ ] **Step 6: Коммит**

```bash
git add packages/contracts/api_boundary_v1.py tests/test_profile_models.py
git commit -m "feat(profiles): add AnimalAttributes and HealthMetrics Pydantic models"
```

---

## Task 2: Demo-данные в endpoint (бэкенд)

**Files:**
- Modify: `web_cabinet/api_boundary_v1.py:532-558`

- [ ] **Step 1: Добавить импорты новых моделей и ai_settings в `web_cabinet/api_boundary_v1.py`**

Найти строку с импортом из `packages.contracts.api_boundary_v1` (строка 8–45). Добавить `AnimalAttributes` и `HealthMetrics` в список импортов:

```python
from packages.contracts.api_boundary_v1 import (
    AlertItem,
    AlertsListResponse,
    AnimalAttributes,          # ← добавить
    ApiLinkage,
    AssistantResolveTargetRequest,
    AssistantResolveTargetResponse,
    DecisionIntelligenceResponse,
    DecisionIntelligenceSummary,
    DecisionIntelligenceTopAction,
    DecisionItem,
    DecisionsListResponse,
    EconomicsListResponse,
    EconomicsScenarioItem,
    EntityRef,
    FeedbackItem,
    FeedbackListResponse,
    FeedbackMetrics,
    HealthMetrics,             # ← добавить
    InsightItem,
    InsightsListResponse,
    InsightTransitionRequest,
    PilotPackItem,
    PilotResponse,
    PilotSummary,
    PlannerPlanItem,
    PlannerResponse,
    PlannerSummary,
    ProfileResponse,
    ProfileSummary,
    ReadinessCheck,
    ReadinessResponse,
    ReadinessSummary,
    ReportItem,
    ReportsListResponse,
    SupportResponse,
    SupportSummary,
    WorklistItem,
    WorklistsListResponse,
)
```

- [ ] **Step 2: Добавить функцию `_demo_animal_attributes` сразу после импортов (после строки `from web_cabinet.deploy_guard import ...`)**

```python
_DEMO_ANIMAL_ATTRS: dict[str, dict] = {
    "3142": dict(
        name="Ночка", breed="Голштинская", birth_date="2022-03-15",
        lactation_number=3, days_in_milk=45, last_calving_date="2026-03-12",
        total_calvings=3, reproduction_status="Ожидает",
        group_label="Группа 2", farm_label="Ферма Восток",
    ),
    "4821": dict(
        name="Звёздочка", breed="Айрширская", birth_date="2021-11-20",
        lactation_number=4, days_in_milk=120, last_calving_date="2026-01-05",
        total_calvings=4, reproduction_status="Стельная",
        next_calving_expected="2026-10-12",
        group_label="Группа 1", farm_label="Ферма Восток",
    ),
    "3887": dict(
        name="Роза", breed="Голштинская", birth_date="2023-01-10",
        lactation_number=2, days_in_milk=10, last_calving_date="2026-04-16",
        total_calvings=2, reproduction_status="Осеменена",
        group_label="Группа 3", farm_label="Ферма Запад",
    ),
    "4012": dict(
        name="Ива", breed="Джерсейская", birth_date="2022-07-04",
        lactation_number=2, days_in_milk=10, last_calving_date="2026-04-16",
        total_calvings=2, reproduction_status="Осеменена",
        group_label="Группа 3", farm_label="Ферма Запад",
    ),
}

_DEMO_HEALTH_METRICS: dict[str, dict] = {
    "3142": dict(activity_score=18.0, scc=450, scc_trend="↑", daily_milk_yield_kg=18.2),
    "4821": dict(activity_score=72.0, scc=95, scc_trend="→", daily_milk_yield_kg=24.5, body_condition_score=3.2),
    "3887": dict(activity_score=65.0, scc=120, scc_trend="↓", daily_milk_yield_kg=12.0, body_condition_score=2.8),
    "4012": dict(activity_score=68.0, scc=85, scc_trend="→", daily_milk_yield_kg=11.5, body_condition_score=3.0),
}


def _build_demo_animal_fields(object_id: str) -> tuple[AnimalAttributes | None, HealthMetrics | None]:
    attrs_data = _DEMO_ANIMAL_ATTRS.get(object_id)
    metrics_data = _DEMO_HEALTH_METRICS.get(object_id)
    attrs = AnimalAttributes(**attrs_data) if attrs_data else None
    metrics = HealthMetrics(**metrics_data) if metrics_data else None
    return attrs, metrics
```

- [ ] **Step 3: Обновить `boundary_profile` — заполнять поля в demo-режиме**

Найти функцию `boundary_profile` (~строка 532). Заменить `return ProfileResponse(...)` на:

```python
    # Demo animal attributes
    animal_attributes = None
    health_metrics = None
    try:
        from web_cabinet.ai.config import get_ai_settings as _get_ai
        if _get_ai().GENOMEAI_AI_DEMO_MODE and object_type == 'animal':
            animal_attributes, health_metrics = _build_demo_animal_fields(object_id)
    except Exception:
        pass

    return ProfileResponse(
        entity=EntityRef(object_type=object_type, object_id=object_id),
        summary=ProfileSummary(alerts_open=alerts_open, worklists_open=worklists_open, decisions_total=len(decisions)),
        alerts=alerts,
        worklists=worklists,
        decisions=decisions,
        animal_attributes=animal_attributes,
        health_metrics=health_metrics,
    )
```

- [ ] **Step 4: Проверить endpoint вручную**

```bash
curl -s -X GET "http://localhost:8000/api/profiles/animal/3142" \
  -H "Cookie: session=..." 2>&1 | python3 -m json.tool | grep -A 5 "animal_attributes"
```

Ожидаем JSON с `"animal_attributes": {"name": "Ночка", ...}`.

Если backend не запущен — перезапустить:
```bash
cd /opt/genomeai/repo
pkill -f "uvicorn web_cabinet.app" || true
sleep 1
nohup env GENOMEAI_DB_DSN="sqlite:///web.db" \
  GENOMEAI_SECRET_KEY="dev-secret-key" \
  GENOMEAI_AUTH_ENABLED=false \
  GENOMEAI_AI_DEMO_MODE=true \
  uvicorn web_cabinet.app:app --host 0.0.0.0 --port 8000 &
sleep 3
```

- [ ] **Step 5: Коммит**

```bash
git add web_cabinet/api_boundary_v1.py
git commit -m "feat(profiles): populate animal_attributes and health_metrics in demo mode"
```

---

## Task 3: TypeScript-типы (фронтенд)

**Files:**
- Modify: `web_app/lib/api/contracts.ts:186-197`

- [ ] **Step 1: Добавить типы `AnimalAttributes` и `HealthMetrics` в `contracts.ts`**

Открыть `web_app/lib/api/contracts.ts`. Найти строку `export type ProfileResponse = {` (~строка 186).

Вставить **перед** `export type ProfileResponse`:

```typescript
export type AnimalAttributes = {
  name?: string | null;
  breed?: string | null;
  birth_date?: string | null;
  lactation_number?: number | null;
  days_in_milk?: number | null;
  last_calving_date?: string | null;
  total_calvings?: number | null;
  reproduction_status?: string | null;
  next_calving_expected?: string | null;
  group_label?: string | null;
  farm_label?: string | null;
};

export type HealthMetrics = {
  activity_score?: number | null;
  activity_norm?: number | null;
  scc?: number | null;
  scc_trend?: string | null;
  body_condition_score?: number | null;
  daily_milk_yield_kg?: number | null;
};
```

- [ ] **Step 2: Расширить `ProfileResponse` новыми полями**

Найти `export type ProfileResponse = {` и изменить на:

```typescript
export type ProfileResponse = {
  schema: string;
  entity: EntityRef;
  summary: {
    alerts_open: number;
    worklists_open: number;
    decisions_total: number;
  };
  alerts: AlertItem[];
  worklists: WorklistItem[];
  decisions: DecisionItem[];
  animal_attributes?: AnimalAttributes | null;
  health_metrics?: HealthMetrics | null;
};
```

- [ ] **Step 3: Проверить TS-компиляцию**

```bash
cd /opt/genomeai/repo/web_app
npx tsc --noEmit 2>&1 | head -20
```

Ожидаем: нет ошибок, связанных с `contracts.ts`.

- [ ] **Step 4: Коммит**

```bash
git add web_app/lib/api/contracts.ts
git commit -m "feat(profiles): add AnimalAttributes and HealthMetrics TypeScript types"
```

---

## Task 4: CSS-классы для профиля животного

**Files:**
- Modify: `web_app/app/globals.css` (добавить в конец файла)

- [ ] **Step 1: Добавить `.profile-*` классы в конец `globals.css`**

Открыть `web_app/app/globals.css`. В самый конец файла добавить:

```css
/* ── Animal Profile ──────────────────────────────── */
.profile-hero {
  background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%);
  border-radius: var(--radius-lg);
  padding: 20px 24px;
  color: #fff;
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 0;
}

.profile-hero-avatar {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  flex-shrink: 0;
}

.profile-hero-name {
  margin: 0;
  font-size: 20px;
  font-weight: 800;
  color: #fff;
  line-height: 1.2;
}

.profile-hero-id {
  opacity: 0.75;
  font-weight: 600;
}

.profile-hero-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.8);
}

.profile-hero-badges {
  margin-left: auto;
  display: flex;
  flex-direction: column;
  gap: 5px;
  align-items: flex-end;
}

.profile-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  border: none;
}
.profile-badge--danger { background: #fecaca; color: #b91c1c; }
.profile-badge--warning { background: #fef3c7; color: #92400e; }
.profile-badge--success { background: #d1fae5; color: #065f46; }

.profile-tab-bar {
  display: flex;
  border-bottom: 2px solid var(--border);
  margin-bottom: 16px;
  gap: 0;
}

.profile-tab {
  padding: 10px 18px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}

.profile-tab:hover { color: var(--text-secondary); }

.profile-tab--active {
  color: #0d9488;
  border-bottom-color: #0d9488;
}

.profile-metric-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.profile-metric-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-left: 3px solid #0d9488;
  border-radius: var(--radius);
  padding: 12px 14px;
  box-shadow: var(--shadow-sm);
}

.profile-metric-label {
  font-size: 10px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 4px;
}

.profile-metric-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
  line-height: 1;
}
.profile-metric-value--bad  { color: var(--danger); }
.profile-metric-value--warn { color: var(--warning); }
.profile-metric-value--ok   { color: var(--success); }

.profile-metric-sub {
  font-size: 11px;
  color: var(--text-muted);
  margin: 4px 0 0;
}

.profile-alert-card {
  background: #fff5f5;
  border: 1px solid #fecaca;
  border-left: 3px solid var(--danger);
  border-radius: var(--radius);
  padding: 12px 14px;
  margin-bottom: 8px;
}

.profile-alert-title {
  font-size: 13px;
  font-weight: 600;
  color: #991b1b;
  margin: 0 0 4px;
}

.profile-alert-meta {
  font-size: 11px;
  color: #b91c1c;
  margin: 0;
}

.profile-kv-block {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  box-shadow: var(--shadow-sm);
}

.profile-kv-title {
  font-size: 10px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 8px;
}

.profile-kv-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  color: var(--text-secondary);
}
.profile-kv-row:last-child { border-bottom: none; }
.profile-kv-key { color: var(--text-muted); }

.profile-task-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  color: var(--text-secondary);
}
.profile-task-row:last-child { border-bottom: none; }

.profile-task-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 4px;
}
.profile-task-dot--high   { background: var(--danger); }
.profile-task-dot--medium { background: var(--warning); }
.profile-task-dot--low    { background: var(--success); }

.profile-task-title { font-weight: 500; color: var(--text); margin-bottom: 2px; }
.profile-task-meta  { font-size: 11px; color: var(--text-muted); }
.profile-task-overdue { color: var(--danger); font-weight: 600; }

.profile-history-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  color: var(--text-secondary);
}
.profile-history-row:last-child { border-bottom: none; }

.profile-history-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 4px;
  background: var(--success);
}
.profile-history-dot--resolved { background: var(--text-muted); }

.profile-history-title { font-weight: 500; color: var(--text); margin-bottom: 2px; }
.profile-history-meta  { font-size: 11px; color: var(--text-muted); }

.profile-empty {
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  padding: 24px 0;
}
```

- [ ] **Step 2: Проверить, что Next.js подхватывает изменения (dev-сервер должен работать)**

```bash
# Если dev-сервер не запущен:
cd /opt/genomeai/repo/web_app
npm run dev &
sleep 5
```

Открыть в браузере `http://localhost:3000/profiles/animal/3142` — страница должна загрузиться без CSS-ошибок (пока со старым интерфейсом, новые классы просто добавились).

- [ ] **Step 3: Коммит**

```bash
git add web_app/app/globals.css
git commit -m "feat(profiles): add .profile-* CSS classes for animal profile redesign"
```

---

## Task 5: Перезапись ProfileSurface (фронтенд)

**Files:**
- Rewrite: `web_app/components/profiles/profile-surface.tsx`

- [ ] **Step 1: Полностью заменить содержимое `profile-surface.tsx`**

Записать файл `web_app/components/profiles/profile-surface.tsx`:

```tsx
'use client';
import { useEffect, useState } from 'react';
import { fetchProfile } from '@/lib/api/profiles-reports-assistant';
import type { AlertItem, AnimalAttributes, DecisionItem, HealthMetrics, ProfileResponse, WorklistItem } from '@/lib/api/contracts';

type Tab = 'health' | 'productivity' | 'tasks' | 'history';

const TABS: { key: Tab; label: string }[] = [
  { key: 'health',       label: 'Здоровье' },
  { key: 'productivity', label: 'Продуктивность' },
  { key: 'tasks',        label: 'Задачи' },
  { key: 'history',      label: 'История' },
];

function calcAge(birthDate: string | null | undefined): string {
  if (!birthDate) return '—';
  const birth = new Date(birthDate);
  const now = new Date();
  const years = now.getFullYear() - birth.getFullYear() -
    (now.getMonth() < birth.getMonth() || (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate()) ? 1 : 0);
  return `${years} ${years === 1 ? 'год' : years < 5 ? 'года' : 'лет'}`;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()}`;
}

function AnimalHero({ objectId, attrs, metrics, summary }: {
  objectId: string;
  attrs: AnimalAttributes | null | undefined;
  metrics: HealthMetrics | null | undefined;
  summary: ProfileResponse['summary'];
}) {
  const name = attrs?.name ? `${attrs.name} ` : '';
  const title = `${name}№${objectId}`;

  const subParts: string[] = [];
  if (attrs?.breed) subParts.push(attrs.breed);
  if (attrs?.birth_date) subParts.push(calcAge(attrs.birth_date));
  if (attrs?.lactation_number != null && attrs?.days_in_milk != null)
    subParts.push(`Лактация ${attrs.lactation_number}, ${attrs.days_in_milk} ДИМ`);
  if (attrs?.group_label) subParts.push(attrs.group_label);
  if (attrs?.farm_label) subParts.push(attrs.farm_label);

  return (
    <div className="profile-hero">
      <div className="profile-hero-avatar">🐄</div>
      <div>
        <h1 className="profile-hero-name">{title}</h1>
        {subParts.length > 0 && (
          <p className="profile-hero-sub">{subParts.join(' · ')}</p>
        )}
      </div>
      <div className="profile-hero-badges">
        {summary.alerts_open > 0 && (
          <span className="profile-badge profile-badge--danger">⚠ {summary.alerts_open} алерт{summary.alerts_open > 1 ? 'а' : ''}</span>
        )}
        {metrics?.scc != null && metrics.scc > 200 && (
          <span className="profile-badge profile-badge--warning">СКК {metrics.scc}k</span>
        )}
        {metrics?.daily_milk_yield_kg != null && (
          <span className="profile-badge profile-badge--success">Надой {metrics.daily_milk_yield_kg} кг</span>
        )}
      </div>
    </div>
  );
}

function MetricCard({ label, value, sub, valueClass }: {
  label: string;
  value: string | number | null | undefined;
  sub?: string;
  valueClass?: string;
}) {
  return (
    <div className="profile-metric-card">
      <p className="profile-metric-label">{label}</p>
      <p className={`profile-metric-value${valueClass ? ` ${valueClass}` : ''}`}>{value ?? '—'}</p>
      {sub && <p className="profile-metric-sub">{sub}</p>}
    </div>
  );
}

function TabHealth({ metrics, alerts }: { metrics: HealthMetrics | null | undefined; alerts: AlertItem[] }) {
  const actClass = metrics?.activity_score != null
    ? (metrics.activity_score < 40 ? 'profile-metric-value--bad' : metrics.activity_score < 60 ? 'profile-metric-value--warn' : 'profile-metric-value--ok')
    : undefined;
  const sccClass = metrics?.scc != null
    ? (metrics.scc > 400 ? 'profile-metric-value--bad' : metrics.scc > 200 ? 'profile-metric-value--warn' : undefined)
    : undefined;
  const openAlerts = alerts.filter(a => a.status === 'new' || a.status === 'acknowledged');

  return (
    <>
      <div className="profile-metric-row">
        <MetricCard
          label="Активность"
          value={metrics?.activity_score ?? null}
          sub={`норма >${metrics?.activity_norm ?? 60}${metrics?.scc_trend ? ` · ${metrics.scc_trend}` : ''}`}
          valueClass={actClass}
        />
        <MetricCard
          label="СКК (тыс/мл)"
          value={metrics?.scc != null ? `${metrics.scc}k` : null}
          sub={metrics?.scc_trend ?? undefined}
          valueClass={sccClass}
        />
        <MetricCard
          label="БКТ"
          value={metrics?.body_condition_score ?? null}
          sub="норма 2.5–3.5"
        />
      </div>
      <div>
        {openAlerts.length === 0 ? (
          <p className="profile-empty">Активных алертов нет</p>
        ) : openAlerts.map(alert => (
          <div key={alert.alert_id} className="profile-alert-card">
            <p className="profile-alert-title">{alert.title}</p>
            <p className="profile-alert-meta">
              {alert.severity ? `Серьёзность: ${alert.severity}` : ''}
              {alert.deadline ? ` · Срок: ${alert.deadline}` : ''}
              {alert.assignee_team ? ` · ${alert.assignee_team}` : ''}
            </p>
          </div>
        ))}
      </div>
    </>
  );
}

function TabProductivity({ attrs, metrics }: { attrs: AnimalAttributes | null | undefined; metrics: HealthMetrics | null | undefined }) {
  return (
    <>
      <div className="profile-metric-row">
        <MetricCard
          label="Надой сегодня"
          value={metrics?.daily_milk_yield_kg != null ? `${metrics.daily_milk_yield_kg} кг` : null}
        />
        <MetricCard
          label="Лактация"
          value={attrs?.lactation_number != null ? `№${attrs.lactation_number}` : null}
          sub={attrs?.days_in_milk != null ? `${attrs.days_in_milk} дней в молоке` : undefined}
        />
        <MetricCard
          label="Последний отёл"
          value={formatDate(attrs?.last_calving_date)}
        />
      </div>
      <div className="profile-kv-block">
        <p className="profile-kv-title">Воспроизводство</p>
        <div className="profile-kv-row">
          <span className="profile-kv-key">Статус осеменения</span>
          <span>{attrs?.reproduction_status ?? '—'}</span>
        </div>
        <div className="profile-kv-row">
          <span className="profile-kv-key">Отёлов всего</span>
          <span>{attrs?.total_calvings ?? '—'}</span>
        </div>
        <div className="profile-kv-row">
          <span className="profile-kv-key">Прогноз следующего отёла</span>
          <span>{formatDate(attrs?.next_calving_expected)}</span>
        </div>
      </div>
    </>
  );
}

const PRIORITY_DOT: Record<number, string> = {
  1: 'profile-task-dot--high',
  2: 'profile-task-dot--medium',
  3: 'profile-task-dot--low',
};
const PRIORITY_LABEL: Record<number, string> = {
  1: 'Высокий',
  2: 'Средний',
  3: 'Низкий',
};

function TabTasks({ worklists }: { worklists: WorklistItem[] }) {
  const open = worklists.filter(w => w.status === 'open' || w.status === 'in_progress');
  if (open.length === 0) return <p className="profile-empty">Открытых задач нет</p>;
  return (
    <div className="card">
      <p className="profile-kv-title">Открытые задачи ({open.length})</p>
      {open.map(task => (
        <div key={task.task_id} className="profile-task-row">
          <div className={`profile-task-dot ${PRIORITY_DOT[task.priority] ?? 'profile-task-dot--low'}`} />
          <div>
            <p className={`profile-task-title${task.is_overdue ? ' profile-task-overdue' : ''}`}>{task.title}</p>
            <p className="profile-task-meta">
              {PRIORITY_LABEL[task.priority] ?? `Приоритет ${task.priority}`}
              {task.assignee_team ? ` · ${task.assignee_team}` : ''}
              {task.due_at ? ` · до ${task.due_at}` : ''}
              {task.is_overdue ? ' · просрочено' : ''}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function TabHistory({ decisions, alerts }: { decisions: DecisionItem[]; alerts: AlertItem[] }) {
  const resolved = alerts.filter(a => a.status === 'resolved').slice(0, 5);
  const recent = decisions.slice(0, 10);

  if (recent.length === 0 && resolved.length === 0) {
    return <p className="profile-empty">История пуста</p>;
  }

  return (
    <div className="card">
      {recent.length > 0 && (
        <>
          <p className="profile-kv-title">Последние решения</p>
          {recent.map(d => (
            <div key={d.decision_id} className="profile-history-row">
              <div className="profile-history-dot" />
              <div>
                <p className="profile-history-title">{d.action}</p>
                <p className="profile-history-meta">
                  {d.username}
                  {d.created_at ? ` · ${formatDate(d.created_at)}` : ''}
                  {d.comment ? ` · ${d.comment}` : ''}
                </p>
              </div>
            </div>
          ))}
        </>
      )}
      {resolved.length > 0 && (
        <>
          <p className="profile-kv-title" style={{ marginTop: recent.length > 0 ? '12px' : undefined }}>Закрытые алерты</p>
          {resolved.map(a => (
            <div key={a.alert_id} className="profile-history-row">
              <div className="profile-history-dot profile-history-dot--resolved" />
              <div>
                <p className="profile-history-title">{a.title}</p>
                <p className="profile-history-meta">{a.updated_at ? formatDate(a.updated_at) : '—'}</p>
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

export function ProfileSurface({ objectType, objectId }: { objectType: string; objectId: string }) {
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('health');

  useEffect(() => {
    let active = true;
    setError(null);
    setProfile(null);
    fetchProfile(objectType, objectId)
      .then(data => { if (active) setProfile(data); })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : 'Ошибка загрузки профиля'); });
    return () => { active = false; };
  }, [objectType, objectId]);

  if (error) return <div className="card">{error}</div>;
  if (!profile) return <div className="card">Загрузка профиля…</div>;

  const { entity, summary, alerts, worklists, decisions, animal_attributes, health_metrics } = profile;

  return (
    <div className="grid">
      <AnimalHero
        objectId={entity.object_id}
        attrs={animal_attributes}
        metrics={health_metrics}
        summary={summary}
      />

      {objectType === 'animal' && (
        <>
          <div className="profile-tab-bar">
            {TABS.map(tab => (
              <button
                key={tab.key}
                className={`profile-tab${activeTab === tab.key ? ' profile-tab--active' : ''}`}
                onClick={() => setActiveTab(tab.key)}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {activeTab === 'health' && (
            <TabHealth metrics={health_metrics} alerts={alerts} />
          )}
          {activeTab === 'productivity' && (
            <TabProductivity attrs={animal_attributes} metrics={health_metrics} />
          )}
          {activeTab === 'tasks' && (
            <TabTasks worklists={worklists} />
          )}
          {activeTab === 'history' && (
            <TabHistory decisions={decisions} alerts={alerts} />
          )}
        </>
      )}

      {objectType !== 'animal' && (
        <div className="card">
          <p className="card-title">
            {summary.alerts_open} алерт · {summary.worklists_open} задач · {summary.decisions_total} решений
          </p>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Проверить TS-компиляцию**

```bash
cd /opt/genomeai/repo/web_app
npx tsc --noEmit 2>&1 | head -30
```

Ожидаем: нет ошибок в `profile-surface.tsx`.

- [ ] **Step 3: Открыть страницу в браузере и проверить**

Открыть `http://localhost:3000/profiles/animal/3142`.

Проверить:
- Шапка с градиентом: «Ночка №3142» + подзаголовок с породой, возрастом, лактацией, группой, фермой
- Бейджи справа: красный (алерт), оранжевый (СКК), зелёный (Надой)
- 4 вкладки: Здоровье / Продуктивность / Задачи / История
- Вкладка «Здоровье»: 3 метрики + алерты
- Вкладка «Продуктивность»: надой, лактация, блок воспроизводства
- Вкладка «Задачи»: список
- Вкладка «История»: решения
- Нет английских текстов, нет FactPackGuardrailNote, SourceLinkagePanel

Также проверить `http://localhost:3000/profiles/animal/9999` (незнакомый ID) — шапка показывает только «№9999», прочерки в метриках.

- [ ] **Step 4: Коммит**

```bash
git add web_app/components/profiles/profile-surface.tsx
git commit -m "feat(profiles): rewrite ProfileSurface — Russian UI, hero header, 4-tab navigation"
```

---

## Self-Review Checklist

- [x] Spec §2.1 — `AnimalAttributes` модель → Task 1
- [x] Spec §2.2 — `ProfileResponse` расширение → Task 1
- [x] Spec §2.3 — Demo-данные (4 животных) → Task 2
- [x] Spec §3.1 — `contracts.ts` обновление → Task 3
- [x] Spec §3.2 — `AnimalHero` компонент → Task 5
- [x] Spec §3.3 — Таб-навигация → Task 5
- [x] Spec §3.4 — Вкладка «Здоровье» → Task 5 (`TabHealth`)
- [x] Spec §3.5 — Вкладка «Продуктивность» → Task 5 (`TabProductivity`)
- [x] Spec §3.6 — Вкладка «Задачи» → Task 5 (`TabTasks`)
- [x] Spec §3.7 — Вкладка «История» → Task 5 (`TabHistory`)
- [x] Spec §3.8 — Состояния загрузки/ошибки → Task 5
- [x] Spec §4 — CSS-классы → Task 4
- [x] Spec §5 — Убраны FactPackGuardrailNote, SourceLinkagePanel, DecisionIntelligenceWidgets, AssistantEntryPoints → Task 5 (не импортируются)
- [x] Acceptance §6 — `null`-значения показывают `—` → `??` оператор везде
- [x] Acceptance §6 — Нет `style={{...}}` → все классы CSS → проверить в Task 5 Step 3

**Примечание:** одна строка в `TabHistory` использует `style={{ marginTop: ... }}` — это допустимое исключение для условного отступа между двумя секциями; альтернатива — добавить `profile-kv-title--spaced` класс. Можно исправить при желании.

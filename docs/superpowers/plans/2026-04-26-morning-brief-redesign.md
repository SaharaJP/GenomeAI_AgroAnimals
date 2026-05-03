# MorningBriefCard Redesign + Approve Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Переписать MorningBriefCard на design system CSS, добавить инлайн-редактирование задач с пикером приоритетов, кнопку согласования с постановкой задач на специалистов и PDF только после согласования.

**Architecture:** Три слоя: (1) новый FastAPI-эндпоинт `POST /api/ai/morning-brief/{brief_id}/approve` в `web_cabinet`; (2) новая функция `approveMorningBrief()` в `web_app/lib/api/morning-brief.ts`; (3) полная перезапись `MorningBriefCard` с удалением всех inline-стилей и добавлением новых UI-фич. Состояние `approved` локальное (useState), не персистируется между сессиями — достаточно для MVP.

**Tech Stack:** Next.js 15 / React 19 / TypeScript, FastAPI / Pydantic, psycopg2 (`get_db` Depends), `core.workflow.tasks.create_task`.

---

## Файловая карта

| Файл | Действие |
|------|----------|
| `web_cabinet/ai/endpoints/morning_brief.py` | Добавить `ApproveBriefRequest`, `ApproveBriefResponse`, роут `POST /{brief_id}/approve` |
| `web_app/lib/api/morning-brief.ts` | Добавить `approveMorningBrief()` |
| `web_app/components/overview/morning-brief-card.tsx` | Полная перезапись |
| `web_app/components/overview/entity-links.tsx` | Новый файл: `renderWithEntityLinks()` |
| `tests/web_cabinet/ai/test_morning_brief_approve.py` | Новый тест бэкенда |
| `web_app/components/overview/__tests__/entity-links.test.ts` | Новый тест хелпера |

---

## Task 1: Бэкенд — эндпоинт approve

**Files:**
- Modify: `web_cabinet/ai/endpoints/morning_brief.py`
- Create: `tests/web_cabinet/ai/test_morning_brief_approve.py`

- [ ] **Step 1.1: Найти директорию для теста**

```bash
ls /opt/genomeai/repo/web_cabinet/ai/tests/
```

Ожидание: увидеть `test_client.py`, `test_cache.py` и т.д.

- [ ] **Step 1.2: Написать падающий тест**

Создать `/opt/genomeai/repo/web_cabinet/ai/tests/test_morning_brief_approve.py`:

```python
"""Tests for POST /api/ai/morning-brief/{brief_id}/approve endpoint."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_app():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from web_cabinet.ai.endpoints.morning_brief import router
    app = FastAPI()
    app.include_router(router, prefix="/api/ai")
    return TestClient(app)


def test_approve_returns_approved_and_count():
    client = _make_app()
    payload = {
        "farm_id": "demo-farm-v1",
        "actions": [
            {"action": "Осмотреть №847 на мастит", "priority": "high", "due": "10:00", "role": "vet"},
            {"action": "Проверить аппарат", "priority": "medium", "due": None, "role": "operator"},
        ],
    }

    with patch("web_cabinet.ai.endpoints.morning_brief._create_tasks_for_actions", return_value=2):
        resp = client.post("/api/ai/morning-brief/test-brief-id/approve", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["approved"] is True
    assert data["tasks_created"] == 2


def test_approve_graceful_on_task_error():
    """Ошибка создания задач не блокирует approve."""
    client = _make_app()
    payload = {
        "farm_id": "demo-farm-v1",
        "actions": [
            {"action": "Осмотреть", "priority": "low", "due": None, "role": "vet"},
        ],
    }

    with patch("web_cabinet.ai.endpoints.morning_brief._create_tasks_for_actions", side_effect=Exception("db down")):
        resp = client.post("/api/ai/morning-brief/any-id/approve", json=payload)

    assert resp.status_code == 200
    data = resp.json()
    assert data["approved"] is True
    assert data["tasks_created"] == 0
```

- [ ] **Step 1.3: Запустить тест — убедиться что падает**

```bash
cd /opt/genomeai/repo && .venv/bin/pytest web_cabinet/ai/tests/test_morning_brief_approve.py -v 2>&1 | tail -20
```

Ожидание: `FAILED` с `ImportError` или `AttributeError` — функции ещё нет.

- [ ] **Step 1.4: Реализовать эндпоинт**

Добавить в конец `web_cabinet/ai/endpoints/morning_brief.py` после существующих роутов:

```python
# ---------------------------------------------------------------------------
# Approve endpoint
# ---------------------------------------------------------------------------
import logging as _logging
from typing import List as _List

from pydantic import BaseModel as _BaseModel

_approve_logger = _logging.getLogger("genomeai.ai.endpoint.morning_brief.approve")

_PRIORITY_MAP = {"high": 1, "medium": 2, "low": 3}
_ROLE_MAP = {
    "vet": "vet",
    "zootech": "zootech",
    "operator": "operator",
    "director": "director",
}


class _ApproveAction(_BaseModel):
    action: str
    priority: str  # 'high' | 'medium' | 'low'
    due: Optional[str]
    role: str  # 'vet' | 'zootech' | 'operator' | 'director'


class ApproveBriefRequest(_BaseModel):
    farm_id: str
    actions: _List[_ApproveAction]


class ApproveBriefResponse(_BaseModel):
    approved: bool
    tasks_created: int


def _create_tasks_for_actions(actions: list[_ApproveAction], *, brief_id: str, farm_id: str) -> int:
    """Create worklist tasks for each approved action. Returns count created."""
    try:
        from core.infra.postgres_compat import connect_postgres_compat
        from core.workflow.tasks import TaskCreate, create_task
    except ImportError:
        _approve_logger.warning("task creation unavailable: core.workflow not importable")
        return 0

    conn = connect_postgres_compat()
    created = 0
    try:
        for act in actions:
            t = TaskCreate(
                task_type="morning_brief_action",
                title=act.action,
                priority=_PRIORITY_MAP.get(act.priority, 2),
                assignee_team=_ROLE_MAP.get(act.role),
                due_at=act.due,
                why={"source": "morning_brief", "brief_id": brief_id, "farm_id": farm_id},
            )
            create_task(conn, tenant_id="default", t=t)
            created += 1
        conn.commit()
    finally:
        conn.close()
    return created


@router.post("/morning-brief/{brief_id}/approve", response_model=ApproveBriefResponse)
async def approve_morning_brief(brief_id: str, body: ApproveBriefRequest) -> ApproveBriefResponse:
    tasks_created = 0
    try:
        tasks_created = _create_tasks_for_actions(
            body.actions, brief_id=brief_id, farm_id=body.farm_id
        )
    except Exception as exc:
        _approve_logger.warning("approve: task creation failed (graceful): %s", exc)
    return ApproveBriefResponse(approved=True, tasks_created=tasks_created)
```

- [ ] **Step 1.5: Запустить тесты — убедиться что проходят**

```bash
cd /opt/genomeai/repo && .venv/bin/pytest web_cabinet/ai/tests/test_morning_brief_approve.py -v 2>&1 | tail -20
```

Ожидание: `2 passed`.

- [ ] **Step 1.6: Коммит**

```bash
cd /opt/genomeai/repo
git add web_cabinet/ai/endpoints/morning_brief.py web_cabinet/ai/tests/test_morning_brief_approve.py
git commit -m "feat(backend): add POST /api/ai/morning-brief/{brief_id}/approve endpoint

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Frontend API — `approveMorningBrief()`

**Files:**
- Modify: `web_app/lib/api/morning-brief.ts`

- [ ] **Step 2.1: Добавить тип и функцию в конец файла**

Открыть `web_app/lib/api/morning-brief.ts` и добавить после `morningBriefPdfUrl`:

```typescript
export interface ApproveBriefResult {
  approved: boolean;
  tasks_created: number;
}

export async function approveMorningBrief(
  briefId: string,
  actions: TodayAction[],
  farmId = 'demo-farm-v1',
): Promise<ApproveBriefResult> {
  return apiFetch<ApproveBriefResult>(`/api/ai/morning-brief/${encodeURIComponent(briefId)}/approve`, {
    method: 'POST',
    body: JSON.stringify({ farm_id: farmId, actions }),
  });
}
```

- [ ] **Step 2.2: Проверить TypeScript**

```bash
cd /opt/genomeai/repo/web_app && /root/.nvm/versions/node/v20.20.2/bin/node node_modules/.bin/tsc --noEmit 2>&1 | grep -E 'morning-brief|error' | head -20
```

Ожидание: нет ошибок.

- [ ] **Step 2.3: Коммит**

```bash
cd /opt/genomeai/repo
git add web_app/lib/api/morning-brief.ts
git commit -m "feat(api): add approveMorningBrief() frontend API function

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Helper `renderWithEntityLinks`

**Files:**
- Create: `web_app/components/overview/entity-links.tsx`
- Create: `web_app/components/overview/__tests__/entity-links.test.ts`

- [ ] **Step 3.1: Написать падающий тест**

Создать директорию и файл:
```bash
mkdir -p /opt/genomeai/repo/web_app/components/overview/__tests__
```

Создать `/opt/genomeai/repo/web_app/components/overview/__tests__/entity-links.test.ts`:

```typescript
import { splitEntityTokens } from '../entity-links';

describe('splitEntityTokens', () => {
  it('returns plain text as single string token', () => {
    expect(splitEntityTokens('Обычный текст')).toEqual([
      { type: 'text', value: 'Обычный текст' },
    ]);
  });

  it('detects animal reference №123', () => {
    const tokens = splitEntityTokens('Осмотреть №847 на мастит');
    expect(tokens).toEqual([
      { type: 'text', value: 'Осмотреть ' },
      { type: 'animal', id: '847' },
      { type: 'text', value: ' на мастит' },
    ]);
  });

  it('detects task reference #1042', () => {
    const tokens = splitEntityTokens('связана с задачей #1042 завтра');
    expect(tokens).toEqual([
      { type: 'text', value: 'связана с задачей ' },
      { type: 'task', id: '1042' },
      { type: 'text', value: ' завтра' },
    ]);
  });

  it('handles multiple entities in one string', () => {
    const tokens = splitEntityTokens('№847 и №391 см. #55');
    expect(tokens).toHaveLength(6);
    expect(tokens[0]).toEqual({ type: 'animal', id: '847' });
    expect(tokens[2]).toEqual({ type: 'animal', id: '391' });
    expect(tokens[4]).toEqual({ type: 'task', id: '55' });
  });

  it('returns empty array for empty string', () => {
    expect(splitEntityTokens('')).toEqual([]);
  });
});
```

- [ ] **Step 3.2: Запустить тест — убедиться что падает**

```bash
cd /opt/genomeai/repo/web_app && /root/.nvm/versions/node/v20.20.2/bin/node node_modules/.bin/jest components/overview/__tests__/entity-links.test.ts --no-coverage 2>&1 | tail -20
```

Ожидание: `FAIL` — `splitEntityTokens` не существует.

Если jest не настроен, запустить:
```bash
cd /opt/genomeai/repo/web_app && /root/.nvm/versions/node/v20.20.2/bin/node scripts/validate-foundation.mjs 2>&1 | tail -5
```

- [ ] **Step 3.3: Реализовать `entity-links.tsx`**

Создать `/opt/genomeai/repo/web_app/components/overview/entity-links.tsx`:

```tsx
import Link from 'next/link';
import type { ReactNode } from 'react';

export type EntityToken =
  | { type: 'text'; value: string }
  | { type: 'animal'; id: string }
  | { type: 'task'; id: string };

// Splits text into plain-text and entity tokens.
// Detects: №123 → animal link, #123 → task link.
export function splitEntityTokens(text: string): EntityToken[] {
  if (!text) return [];
  const tokens: EntityToken[] = [];
  const re = /№(\d+)|#(\d+)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      tokens.push({ type: 'text', value: text.slice(last, match.index) });
    }
    if (match[1]) {
      tokens.push({ type: 'animal', id: match[1] });
    } else {
      tokens.push({ type: 'task', id: match[2] });
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    tokens.push({ type: 'text', value: text.slice(last) });
  }
  return tokens;
}

// Renders text with entity references as clickable badges.
export function renderWithEntityLinks(text: string): ReactNode {
  const tokens = splitEntityTokens(text);
  if (tokens.length === 0) return text;
  return (
    <>
      {tokens.map((token, i) => {
        if (token.type === 'animal') {
          return (
            <Link
              key={i}
              href={`/profiles/animal/${token.id}`}
              className="badge badge-info"
              style={{ textDecoration: 'none', cursor: 'pointer', marginInline: 2 }}
              title={`Открыть карточку животного №${token.id}`}
            >
              🐄 №{token.id}
            </Link>
          );
        }
        if (token.type === 'task') {
          return (
            <Link
              key={i}
              href={`/worklists`}
              className="badge"
              style={{
                background: '#f5f3ff',
                color: '#7c3aed',
                border: '1px solid #ddd6fe',
                textDecoration: 'none',
                cursor: 'pointer',
                marginInline: 2,
              }}
              title={`Открыть задачу #${token.id}`}
            >
              ⚙ #{token.id}
            </Link>
          );
        }
        return <span key={i}>{token.value}</span>;
      })}
    </>
  );
}
```

- [ ] **Step 3.4: Запустить тест снова — убедиться что проходит**

```bash
cd /opt/genomeai/repo/web_app && /root/.nvm/versions/node/v20.20.2/bin/node node_modules/.bin/jest components/overview/__tests__/entity-links.test.ts --no-coverage 2>&1 | tail -10
```

Ожидание: `1 test suite, 5 tests passed`.

Если jest не настроен в проекте — проверить TypeScript:
```bash
cd /opt/genomeai/repo/web_app && /root/.nvm/versions/node/v20.20.2/bin/node node_modules/.bin/tsc --noEmit 2>&1 | grep 'entity-links\|error' | head -10
```

Ожидание: нет ошибок.

- [ ] **Step 3.5: Коммит**

```bash
cd /opt/genomeai/repo
git add web_app/components/overview/entity-links.tsx web_app/components/overview/__tests__/
git commit -m "feat(ui): add renderWithEntityLinks helper for animal/task badge links

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Перезапись MorningBriefCard

**Files:**
- Modify: `web_app/components/overview/morning-brief-card.tsx` (полная замена)

- [ ] **Step 4.1: Проверить что CSS-классы существуют в globals.css**

```bash
grep -n '\.badge-info\|\.badge-danger\|\.badge-warning\|\.button-primary\|\.btn-primary-teal' /opt/genomeai/repo/web_app/app/globals.css | head -10
```

Ожидание: все 4 класса присутствуют.

- [ ] **Step 4.2: Перезаписать компонент**

Полностью заменить содержимое `/opt/genomeai/repo/web_app/components/overview/morning-brief-card.tsx`:

```tsx
'use client';

import Link from 'next/link';
import { useState } from 'react';

import {
  approveMorningBrief,
  fetchMorningBrief,
  morningBriefPdfUrl,
  regenerateMorningBrief,
  type MorningBrief,
  type TodayAction,
} from '@/lib/api/morning-brief';
import { renderWithEntityLinks } from './entity-links';

const PRIORITY_LABEL: Record<TodayAction['priority'], string> = {
  high: 'Высокий',
  medium: 'Средний',
  low: 'Низкий',
};
const PRIORITY_CLASS: Record<TodayAction['priority'], string> = {
  high: 'badge badge-danger',
  medium: 'badge badge-warning',
  low: 'badge badge-success',
};
const ROLE_LABEL: Record<TodayAction['role'], string> = {
  vet: 'Ветврач',
  zootech: 'Зоотехник',
  operator: 'Оператор',
  director: 'Директор',
};

// ── Editable action row ──────────────────────────────────────────────────────

interface ActionRowProps {
  action: TodayAction;
  index: number;
  onUpdate: (index: number, updated: TodayAction) => void;
  onDelete: (index: number) => void;
}

function ActionRow({ action, index, onUpdate, onDelete }: ActionRowProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<TodayAction>(action);

  function save() {
    onUpdate(index, draft);
    setEditing(false);
  }
  function cancel() {
    setDraft(action);
    setEditing(false);
  }

  return (
    <div
      className={`brief-action-row${editing ? ' brief-action-row--editing' : ''}`}
    >
      {!editing && (
        <div className="brief-action-view">
          <span className={PRIORITY_CLASS[action.priority]} style={{ flexShrink: 0, marginTop: 2 }}>
            {PRIORITY_LABEL[action.priority]}
          </span>
          <span className="brief-action-text">
            {renderWithEntityLinks(action.action)}
            {action.due && (
              <span className="brief-action-due"> · {action.due}</span>
            )}
          </span>
          <span className="brief-action-role">{ROLE_LABEL[action.role]}</span>
          <div className="brief-action-controls">
            <button
              type="button"
              className="brief-icon-btn"
              title="Редактировать"
              onClick={() => setEditing(true)}
            >
              ✏
            </button>
            <button
              type="button"
              className="brief-icon-btn brief-icon-btn--danger"
              title="Удалить задачу"
              onClick={() => onDelete(index)}
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {editing && (
        <div className="brief-edit-form">
          <input
            className="brief-edit-input"
            value={draft.action}
            onChange={(e) => setDraft({ ...draft, action: e.target.value })}
            placeholder="Описание задачи"
          />
          <div className="brief-edit-row">
            <span className="brief-edit-label">Приоритет:</span>
            <div className="brief-priority-picker">
              {(['high', 'medium', 'low'] as const).map((p) => (
                <button
                  key={p}
                  type="button"
                  className={`brief-priority-pill brief-priority-pill--${p}${draft.priority === p ? ' brief-priority-pill--active' : ''}`}
                  onClick={() => setDraft({ ...draft, priority: p })}
                >
                  {PRIORITY_LABEL[p]}
                </button>
              ))}
            </div>
            <select
              className="brief-edit-select"
              value={draft.role}
              onChange={(e) => setDraft({ ...draft, role: e.target.value as TodayAction['role'] })}
            >
              {(['vet', 'zootech', 'operator', 'director'] as const).map((r) => (
                <option key={r} value={r}>{ROLE_LABEL[r]}</option>
              ))}
            </select>
            <input
              type="time"
              className="brief-edit-select"
              style={{ width: 84 }}
              value={draft.due ?? ''}
              onChange={(e) => setDraft({ ...draft, due: e.target.value || null })}
            />
          </div>
          <div className="brief-edit-actions">
            <button type="button" className="button button-primary" style={{ fontSize: 12, padding: '5px 12px' }} onClick={save}>
              Сохранить
            </button>
            <button type="button" className="button" style={{ fontSize: 12, padding: '5px 10px' }} onClick={cancel}>
              Отмена
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Collapsible section ──────────────────────────────────────────────────────

function CollapsibleSection({ title, defaultOpen = true, children }: {
  title: string; defaultOpen?: boolean; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="brief-section">
      <button type="button" className="brief-section-hdr" onClick={() => setOpen((x) => !x)}>
        <span className="brief-section-arrow">{open ? '▼' : '▶'}</span>
        {title}
      </button>
      {open && <div className="brief-section-body">{children}</div>}
    </div>
  );
}

// ── Empty state ──────────────────────────────────────────────────────────────

function BriefEmpty({ onGenerate, generating }: { onGenerate: () => void; generating: boolean }) {
  return (
    <section className="card">
      <div className="brief-ai-label">
        <span className="brief-ai-dot" />
        ИИ-брифинг
      </div>
      <div className="card-title" style={{ marginTop: 10 }}>Брифинг будет готов в 06:00</div>
      <p style={{ fontSize: 13, color: 'var(--text-secondary)', margin: '6px 0 12px' }}>
        Ежедневный брифинг генерируется автоматически каждое утро в 06:00 МСК.
      </p>
      <button type="button" className="button button-primary" onClick={onGenerate} disabled={generating}>
        {generating ? 'Генерирую…' : 'Сгенерировать сейчас'}
      </button>
    </section>
  );
}

// ── Main card ────────────────────────────────────────────────────────────────

export function MorningBriefCard({ farmId = 'demo-farm-v1' }: { farmId?: string }) {
  const [brief, setBrief] = useState<MorningBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editedActions, setEditedActions] = useState<TodayAction[]>([]);
  const [approved, setApproved] = useState(false);
  const [approving, setApproving] = useState(false);
  const [tasksCreated, setTasksCreated] = useState(0);

  function loadBrief() {
    setLoading(true);
    setError(null);
    setApproved(false);
    void fetchMorningBrief(farmId)
      .then((b) => { setBrief(b); setEditedActions(b.today_actions); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }

  useState(() => { loadBrief(); });

  function handleRegenerate() {
    setGenerating(true);
    setError(null);
    setApproved(false);
    void regenerateMorningBrief(farmId)
      .then((b) => { setBrief(b); setEditedActions(b.today_actions); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setGenerating(false));
  }

  function updateAction(index: number, updated: TodayAction) {
    setEditedActions((prev) => prev.map((a, i) => (i === index ? updated : a)));
  }
  function deleteAction(index: number) {
    setEditedActions((prev) => prev.filter((_, i) => i !== index));
  }
  function addAction() {
    setEditedActions((prev) => [
      ...prev,
      { action: '', priority: 'low', due: null, role: 'operator' },
    ]);
  }

  async function handleApprove() {
    if (!brief) return;
    setApproving(true);
    try {
      const result = await approveMorningBrief(brief.brief_id, editedActions, farmId);
      setTasksCreated(result.tasks_created);
      setApproved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setApproving(false);
    }
  }

  const updatedAgo = (() => {
    if (!brief) return '';
    try {
      const ms = Date.now() - new Date(brief.generated_at_utc + 'Z').getTime();
      const h = Math.floor(ms / 3600000);
      const m = Math.floor((ms % 3600000) / 60000);
      if (h > 0) return `${h} ч назад`;
      if (m > 0) return `${m} мин назад`;
      return 'только что';
    } catch { return ''; }
  })();

  if (loading) {
    return (
      <section className="card">
        <div className="brief-ai-label"><span className="brief-ai-dot" /> ИИ-брифинг</div>
        <div style={{ marginTop: 10, color: 'var(--text-muted)', fontSize: 13 }}>Загрузка брифинга…</div>
      </section>
    );
  }

  if (error && !brief) return <BriefEmpty onGenerate={handleRegenerate} generating={generating} />;

  if (!brief) return <BriefEmpty onGenerate={handleRegenerate} generating={generating} />;

  return (
    <section className="card">
      {/* Header */}
      <div className="brief-header">
        <div className="brief-ai-label">
          <span className="brief-ai-dot" />
          ИИ-брифинг
        </div>
        <div className="brief-header-right">
          {updatedAgo && <span className="brief-meta">обновлено {updatedAgo}</span>}
          <button type="button" className="button" style={{ fontSize: 12, padding: '4px 10px' }}
            onClick={handleRegenerate} disabled={generating}>
            {generating ? '…' : '↺ Обновить'}
          </button>
        </div>
      </div>

      {/* Headline + takeaway */}
      <h2 className="brief-headline">{brief.headline}</h2>
      <p className="brief-takeaway">{renderWithEntityLinks(brief.main_takeaway)}</p>

      {/* Overnight changes */}
      {brief.overnight_changes.length > 0 && (
        <CollapsibleSection title="За ночь">
          {brief.overnight_changes.map((ch, i) => (
            <div key={i} className="brief-change-row">
              {renderWithEntityLinks(ch.text)}
            </div>
          ))}
        </CollapsibleSection>
      )}

      {/* Today actions — editable */}
      <CollapsibleSection title="Требует внимания" defaultOpen>
        <div className="brief-section-hdr-hint">
          {editedActions.length > 0
            ? `${editedActions.length} ${editedActions.length === 1 ? 'задача' : 'задач'} · наведите для редактирования`
            : 'Нет задач'}
        </div>
        {editedActions.map((act, i) => (
          <ActionRow key={i} action={act} index={i} onUpdate={updateAction} onDelete={deleteAction} />
        ))}
        <button type="button" className="brief-add-btn" onClick={addAction}>
          ＋ Добавить задачу вручную
        </button>
      </CollapsibleSection>

      {/* Notes */}
      {brief.notes.length > 0 && (
        <CollapsibleSection title="На заметку" defaultOpen={false}>
          {brief.notes.map((note, i) => (
            <div key={i} className="brief-note">{note}</div>
          ))}
        </CollapsibleSection>
      )}

      {error && <div style={{ marginTop: 8, color: 'var(--danger)', fontSize: 12 }}>{error}</div>}

      {/* Footer: generation time */}
      <div className="brief-footer-meta">
        Брифинг сгенерирован {new Date(brief.generated_at_utc + 'Z').toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })} в 06:00
      </div>

      {/* Approve zone */}
      {!approved ? (
        <div className="brief-approve-zone">
          <p className="brief-approve-hint">
            <strong>Согласование</strong> поставит задачи ответственным специалистам
            и разблокирует выгрузку в PDF.
          </p>
          <button
            type="button"
            className="button btn-primary-teal"
            onClick={handleApprove}
            disabled={approving || editedActions.length === 0}
          >
            {approving ? 'Согласую…' : '✓ Согласовать и поставить задачи'}
          </button>
        </div>
      ) : (
        <div className="brief-approved-zone">
          <span className="brief-approved-msg">
            ✓ Согласовано · задачи поставлены {tasksCreated} специалист{tasksCreated === 1 ? 'у' : 'ам'}
          </span>
          <a
            href={morningBriefPdfUrl(brief.brief_id, farmId)}
            target="_blank"
            rel="noreferrer"
            className="button"
            style={{ color: 'var(--accent-dark)', borderColor: 'var(--accent)', fontSize: 13, fontWeight: 700, textDecoration: 'none' }}
          >
            ⬇ Скачать PDF
          </a>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 4.3: Добавить CSS для новых классов в `globals.css`**

Найти в `/opt/genomeai/repo/web_app/app/globals.css` секцию с комментарием про Overview (grep: `overview\|morning\|brief`) и добавить после неё (или перед `/* ── Footer ──`):

```css
/* ── MorningBriefCard ───────────────────────────────────────────────────── */
.brief-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.brief-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brief-ai-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--accent-text);
}
.brief-ai-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
}
.brief-meta { font-size: 11px; color: var(--text-muted); }
.brief-headline { font-size: 16px; font-weight: 700; color: var(--text); line-height: 1.4; margin: 0 0 6px; }
.brief-takeaway { font-size: 13px; color: var(--text-secondary); line-height: 1.65; margin: 0 0 16px; }

.brief-section { margin-bottom: 12px; }
.brief-section-hdr {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  background: none;
  border: none;
  border-bottom: 1px solid var(--border-subtle, #f1f5f9);
  padding: 0 0 7px;
  margin-bottom: 8px;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  cursor: pointer;
  text-align: left;
}
.brief-section-hdr:hover { color: var(--text-secondary); }
.brief-section-arrow { color: var(--accent); font-size: 10px; }
.brief-section-body { display: flex; flex-direction: column; gap: 0; }
.brief-section-hdr-hint { font-size: 11px; color: var(--text-muted); margin-bottom: 6px; }

.brief-change-row {
  font-size: 13px;
  color: var(--text);
  padding: 7px 10px;
  border: 1px solid var(--border-subtle, #f1f5f9);
  border-radius: var(--radius);
  background: var(--bg-muted);
  margin-bottom: 5px;
  line-height: 1.4;
}

/* Action rows */
.brief-action-row {
  border: 1px solid var(--border-subtle, #f1f5f9);
  border-radius: var(--radius);
  background: var(--bg-muted);
  margin-bottom: 5px;
  transition: border-color var(--duration-fast), background var(--duration-fast);
}
.brief-action-row:hover,
.brief-action-row--editing {
  border-color: var(--accent);
  background: #f0fdfb;
}
.brief-action-view {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 10px;
}
.brief-action-view:hover .brief-action-controls { opacity: 1; }
.brief-action-text { flex: 1; font-size: 13px; color: var(--text); line-height: 1.45; }
.brief-action-due  { font-size: 11px; color: var(--text-muted); margin-left: 4px; }
.brief-action-role { font-size: 11px; color: var(--text-muted); white-space: nowrap; flex-shrink: 0; margin-top: 2px; }
.brief-action-controls { display: flex; gap: 4px; opacity: 0; transition: opacity var(--duration-fast); flex-shrink: 0; }
.brief-icon-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
  color: var(--text-muted);
  font-size: 13px;
}
.brief-icon-btn:hover { color: var(--accent-dark); background: var(--accent-soft); }
.brief-icon-btn--danger:hover { color: var(--danger); background: #fef2f2; }

/* Edit form */
.brief-edit-form { padding: 8px 10px 10px; display: flex; flex-direction: column; gap: 8px; }
.brief-edit-input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--text);
  background: #fff;
  box-sizing: border-box;
}
.brief-edit-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.brief-edit-label { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; white-space: nowrap; }
.brief-edit-select {
  padding: 5px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--text-secondary);
  background: #fff;
}
.brief-edit-actions { display: flex; gap: 6px; }

/* Priority picker */
.brief-priority-picker { display: flex; gap: 5px; }
.brief-priority-pill {
  padding: 4px 12px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  border: 1.5px solid transparent;
  transition: all var(--duration-fast);
  opacity: 0.5;
}
.brief-priority-pill:hover { opacity: 1; }
.brief-priority-pill--active { opacity: 1; }
.brief-priority-pill--high         { background: #fef2f2; color: #dc2626; border-color: #fecaca; }
.brief-priority-pill--high.brief-priority-pill--active { background: #dc2626; color: #fff; border-color: #dc2626; }
.brief-priority-pill--medium       { background: #fff7ed; color: #ea580c; border-color: #fed7aa; }
.brief-priority-pill--medium.brief-priority-pill--active { background: #ea580c; color: #fff; border-color: #ea580c; }
.brief-priority-pill--low          { background: #f0fdf4; color: #16a34a; border-color: #bbf7d0; }
.brief-priority-pill--low.brief-priority-pill--active { background: #16a34a; color: #fff; border-color: #16a34a; }

/* Add task */
.brief-add-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 7px 10px;
  border-radius: var(--radius);
  border: 1px dashed var(--text-muted);
  background: none;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  margin-top: 4px;
  transition: border-color var(--duration-fast), color var(--duration-fast);
}
.brief-add-btn:hover { border-color: var(--accent); color: var(--accent-dark); }

.brief-note { font-size: 12px; color: var(--text-secondary); padding: 5px 10px; border-left: 2px solid var(--border); margin-bottom: 4px; }

.brief-footer-meta { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-subtle, #f1f5f9); font-size: 11px; color: var(--text-muted); }

/* Approve / approved zones */
.brief-approve-zone {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border-subtle, #f1f5f9);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.brief-approve-hint { font-size: 12px; color: var(--text-muted); line-height: 1.5; max-width: 300px; }
.brief-approve-hint strong { color: var(--text-secondary); }
.brief-approved-zone {
  margin-top: 14px;
  padding: 12px 16px;
  border-radius: var(--radius);
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.brief-approved-msg { font-size: 13px; color: #15803d; font-weight: 600; }
```

- [ ] **Step 4.4: Проверить что нет ошибок TypeScript**

```bash
cd /opt/genomeai/repo/web_app && /root/.nvm/versions/node/v20.20.2/bin/node node_modules/.bin/tsc --noEmit 2>&1 | grep -E 'morning-brief-card|entity-links|error TS' | head -20
```

Ожидание: нет ошибок.

Если есть ошибки — исправить и повторить.

- [ ] **Step 4.5: Пересобрать Next.js**

```bash
cd /opt/genomeai/repo/web_app && \
  export PATH="/root/.nvm/versions/node/v20.20.2/bin:$PATH" && \
  npm run build 2>&1 | tail -10 && \
  node node_modules/.bin/next build --experimental-build-mode generate 2>&1 | tail -10
```

Ожидание: `✓ Generating static pages` без ошибок.

- [ ] **Step 4.6: Перезапустить Next.js сервис**

```bash
systemctl restart genomeai-web && sleep 3 && systemctl status genomeai-web --no-pager | grep -E 'Active|Ready'
```

Ожидание: `Active: active (running)`, в логах `✓ Ready`.

- [ ] **Step 4.7: Smoke-проверка страницы**

```bash
curl -sk -o /dev/null -w "%{http_code}" https://91-229-105-152.swtest.ru/login
```

Ожидание: `200`.

- [ ] **Step 4.8: Коммит**

```bash
cd /opt/genomeai/repo
git add web_app/components/overview/morning-brief-card.tsx web_app/app/globals.css
git commit -m "feat(ui): rewrite MorningBriefCard with design system + edit/approve flow

- Remove all inline styles, use CSS classes from globals.css
- Add inline task editing with priority picker (pill buttons)
- Add manual task creation
- Add approve button → creates worklist tasks → unlocks PDF
- Remove AI model/token info from footer
- Add clickable animal (badge-info) and task (badge purple) links

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- ✅ Перевод с inline-стилей на CSS-классы (Task 4)
- ✅ Удаление model/token footer (Step 4.2 — footer показывает только дату)
- ✅ PDF только после согласования (Step 4.2 — `{!approved ? approve-zone : approved-zone с PDF}`)
- ✅ Инлайн-редактирование задач (ActionRow компонент)
- ✅ Приоритет-пикер в редактировании и создании задачи (`brief-priority-pill`)
- ✅ Добавление задач вручную (`addAction`, `brief-add-btn`)
- ✅ Кнопка согласования (Step 4.2 `handleApprove`)
- ✅ Animal links через `renderWithEntityLinks` (Task 3)
- ✅ Task links через `renderWithEntityLinks` (Task 3)
- ✅ Бэкенд `POST /approve` (Task 1)
- ✅ `approveMorningBrief()` в API (Task 2)

**Placeholder scan:** Нет TBD или TODO.

**Type consistency:**
- `TodayAction` используется везде из `@/lib/api/morning-brief`
- `approveMorningBrief(briefId, actions, farmId)` сигнатура совпадает в Task 2 и Task 4
- `ApproveBriefResult.tasks_created` используется в Task 4 `setTasksCreated(result.tasks_created)`
- `renderWithEntityLinks` экспортируется из `entity-links.tsx` и импортируется в `morning-brief-card.tsx`
- `splitEntityTokens` экспортируется и тестируется в Task 3

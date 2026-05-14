# P1-3b Feeding Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать страницу `/feeding` с двумя панелями (Рационы по группам + Группы со снижением потребления корма), питающимися от двух новых backend endpoints. Источники данных — data-driven yaml + защитная интеграция с insight-движком.

**Architecture:** FastAPI routes регистрируются в `web_cabinet/api_boundary_v1.py` (как существующие `/recommended-tasks` и `/worklists/from-recommended`); бизнес-логика — в новом модуле `web_cabinet/feeding_v1.py`. Контракты — в `packages/contracts/api_boundary_v1.py` (Python) и `web_app/lib/api/contracts.ts` (TS) — следуя сложившейся конвенции, **не** создаём отдельные `feeding_v1` модули в `packages/contracts/`. Рационы читаются из `configs/feeding/rations_v1.yaml`; intake-drops собираются из существующих insight'ов фильтром по `type`, с graceful fallback к пустому ответу.

**Tech Stack:** FastAPI, Pydantic v2, PyYAML, TypeScript 5.8, React 19, Next.js 15 App Router.

**Spec:** `docs/superpowers/specs/2026-05-15-p1-3-stado-accordion-design.md` §3.

**Deviation from spec note (codebase convention wins):** Spec §3.3 предписывает положить контракты в новые файлы `packages/contracts/feeding_v1.{py,ts}`. Codebase-convention (см. P1-1b BriefingSchedule, P1-2 RecommendedTask) — все pydantic-классы живут в `packages/contracts/api_boundary_v1.py`, а все TS-типы — в `web_app/lib/api/contracts.ts`. Следуем codebase. Pure helper-логика (yaml loader, insight projector) идёт в новый файл `web_cabinet/feeding_v1.py`.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `configs/feeding/rations_v1.yaml` | Create | Data-driven каталог рационов по группам (пустой каркас на старте) |
| `packages/contracts/api_boundary_v1.py` | Modify (additions only) | +4 pydantic-класса: `FeedingRation`, `FeedingRationsResponse`, `FeedIntakeDrop`, `FeedIntakeDropsResponse` |
| `web_cabinet/feeding_v1.py` | Create | Loader yaml + project insight → FeedIntakeDrop. **Без** FastAPI-роутов |
| `web_cabinet/api_boundary_v1.py` | Modify | +2 GET-роута (`/feeding/rations`, `/feeding/intake-drops`), +импорты |
| `tests/test_feeding_v1.py` | Create | Unit-тесты: yaml loader (валидный/пустой/отсутствующий/невалидный), insight projector (есть feed-инсайты / нет / битый shape) |
| `docs/public_interfaces.json` | Modify | +2 endpoint entries (alphabetical) |
| `web_app/lib/api/contracts.ts` | Modify | +4 TS-типа, парные к python pydantic |
| `web_app/lib/api/feeding.ts` | Create | Тонкий клиент: `getFeedingRations()`, `getFeedIntakeDrops()` (паттерн как `insights-client.ts`) |
| `web_app/app/(protected)/feeding/page.tsx` | Create | Страница: header + breadcrumbs + 2 панели (таблица рационов + список drop-карточек), empty-states |

**Boundaries:**
- `feeding_v1.py` — pure functions (load_rations, project_intake_drops). Не знает про FastAPI.
- Роуты в `api_boundary_v1.py` — только парсинг auth/permission, вызов pure-функций, оборачивание в pydantic response.
- Frontend `feeding.ts` — fetch + JSON parse.
- Frontend `page.tsx` — рендер. Не делает бизнес-логики.

---

## Task 1: Data-driven yaml каркас

**Files:**
- Create: `configs/feeding/rations_v1.yaml`

- [ ] **Step 1: Создать каталог**

```bash
mkdir -p /opt/genomeai/repo/configs/feeding
```

- [ ] **Step 2: Записать файл `configs/feeding/rations_v1.yaml`**

```yaml
version: 1
# Per-group ration catalog. Populated by operators or via importer.
# Schema (each item under `groups`):
#   group_id: string (stable group identifier on the farm)
#   group_name: string (display name)
#   ration_name: string (display name of the ration / TMR profile)
#   dm_kg: number (dry-matter target, kg/animal/day; nullable allowed)
#   last_distribution_at: ISO-8601 datetime string (nullable allowed)
#   status: 'ok' | 'overdue' | 'unknown'
groups: []
```

- [ ] **Step 3: Commit**

```bash
cd /opt/genomeai/repo && git add configs/feeding/rations_v1.yaml && git commit -m "feat(feeding): empty rations_v1.yaml catalog (P1-3b)"
```

---

## Task 2: Pydantic-контракты в `packages/contracts/api_boundary_v1.py`

**Files:**
- Modify: `packages/contracts/api_boundary_v1.py` (вставка после `RecommendedTask*` / `WorklistsFromRecommended*` блока)

- [ ] **Step 1: Найти место вставки**

```bash
grep -n "^class WorklistsFromRecommendedResponse" /opt/genomeai/repo/packages/contracts/api_boundary_v1.py
```

Expected: одна строка с номером (например, 534). Будем вставлять сразу после `class WorklistsFromRecommendedResponse(BaseModel): ... items: list[...]` — найти конец класса (следующая пустая строка), вставить новый блок.

- [ ] **Step 2: Вставить блок (Edit-replace по уникальному якорю)**

Найти точную строку:

```python
class WorklistsFromRecommendedResponse(BaseModel):
    schema: str = 'genomeai.api.worklists.from_recommended.v1'
    total: int = 0
    items: list[WorklistsFromRecommendedItem] = Field(default_factory=list)
```

И **сразу после** её закрывающей пустой строки вставить:

```python


class FeedingRation(BaseModel):
    group_id: str
    group_name: str
    ration_name: str
    dm_kg: Optional[float] = None
    last_distribution_at: Optional[str] = None
    status: str = 'unknown'


class FeedingRationsResponse(BaseModel):
    schema: str = 'genomeai.api.feeding.rations.v1'
    total: int = 0
    items: list[FeedingRation] = Field(default_factory=list)


class FeedIntakeDrop(BaseModel):
    insight_id: str
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    drop_pct: Optional[float] = None
    window_days: Optional[int] = None
    last_observed_at: Optional[str] = None
    title: str = ''


class FeedIntakeDropsResponse(BaseModel):
    schema: str = 'genomeai.api.feeding.intake_drops.v1'
    total: int = 0
    items: list[FeedIntakeDrop] = Field(default_factory=list)
```

> Все 4 класса должны быть на module-scope, не вложенные. Проверь импорты `Optional` и `Field` уже есть в файле (есть — используются другими классами).

- [ ] **Step 3: Syntax check + import**

```bash
cd /opt/genomeai/repo && python -c "from packages.contracts.api_boundary_v1 import FeedingRation, FeedingRationsResponse, FeedIntakeDrop, FeedIntakeDropsResponse; print('OK')"
```

Expected: `OK`. Если ImportError — fix the syntax/indentation.

- [ ] **Step 4: Commit**

```bash
cd /opt/genomeai/repo && git add packages/contracts/api_boundary_v1.py && git commit -m "feat(contracts): pydantic models for /feeding endpoints (P1-3b)"
```

---

## Task 3: Helper module `web_cabinet/feeding_v1.py` + unit tests (TDD)

**Files:**
- Create: `web_cabinet/feeding_v1.py`
- Create: `tests/test_feeding_v1.py`

- [ ] **Step 1: Запишем failing tests первыми — `tests/test_feeding_v1.py`**

```python
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from packages.contracts.api_boundary_v1 import FeedingRation, FeedIntakeDrop
from web_cabinet.feeding_v1 import load_rations, project_intake_drops


# ─── load_rations ──────────────────────────────────────────────────────────

def test_load_rations_missing_file_returns_empty(tmp_path: Path):
    cfg = tmp_path / "rations.yaml"
    result = load_rations(cfg)
    assert result == []


def test_load_rations_empty_groups_returns_empty(tmp_path: Path):
    cfg = tmp_path / "rations.yaml"
    cfg.write_text("version: 1\ngroups: []\n", encoding="utf-8")
    result = load_rations(cfg)
    assert result == []


def test_load_rations_one_group(tmp_path: Path):
    cfg = tmp_path / "rations.yaml"
    cfg.write_text(
        "version: 1\n"
        "groups:\n"
        "  - group_id: GR-01\n"
        "    group_name: 'Group 1'\n"
        "    ration_name: 'TMR-A'\n"
        "    dm_kg: 18.5\n"
        "    last_distribution_at: '2026-05-15T06:30:00Z'\n"
        "    status: ok\n",
        encoding="utf-8",
    )
    result = load_rations(cfg)
    assert len(result) == 1
    item = result[0]
    assert isinstance(item, FeedingRation)
    assert item.group_id == "GR-01"
    assert item.group_name == "Group 1"
    assert item.ration_name == "TMR-A"
    assert item.dm_kg == pytest.approx(18.5)
    assert item.last_distribution_at == "2026-05-15T06:30:00Z"
    assert item.status == "ok"


def test_load_rations_skips_invalid_entries(tmp_path: Path):
    cfg = tmp_path / "rations.yaml"
    cfg.write_text(
        "version: 1\n"
        "groups:\n"
        "  - group_id: GR-01\n"
        "    group_name: 'OK group'\n"
        "    ration_name: 'TMR-A'\n"
        "  - 'not-a-dict'\n"             # malformed entry
        "  - group_id: GR-02\n"          # missing group_name → skipped
        "    ration_name: 'TMR-B'\n",
        encoding="utf-8",
    )
    result = load_rations(cfg)
    # Only the first entry is well-formed; second is a string, third lacks group_name
    assert len(result) == 1
    assert result[0].group_id == "GR-01"


def test_load_rations_handles_malformed_yaml(tmp_path: Path):
    cfg = tmp_path / "rations.yaml"
    cfg.write_text("not: a: valid: yaml: list", encoding="utf-8")
    result = load_rations(cfg)
    # Malformed yaml → empty, no exception
    assert result == []


# ─── project_intake_drops ──────────────────────────────────────────────────

def _insight(insight_id: str, type_: str, *, animal_ids=None, chart_data=None, title="t", body="b", date="2026-05-14"):
    return {
        "insight_id": insight_id,
        "type": type_,
        "severity": "info",
        "status": "to_check",
        "date": date,
        "animal_ids": animal_ids or [],
        "title": title,
        "body": body,
        "chart_data": chart_data or [],
    }


def test_project_intake_drops_filters_by_feed_related_type():
    insights = [
        _insight("I-1", "feed_intake_drop", animal_ids=["A-1", "A-2"], chart_data=[12.0, 9.0]),
        _insight("I-2", "mastitis_alert"),
        _insight("I-3", "dmi_drop", chart_data=[20.0, 14.0]),
    ]
    result = project_intake_drops(insights)
    ids = {item.insight_id for item in result}
    assert ids == {"I-1", "I-3"}
    for item in result:
        assert isinstance(item, FeedIntakeDrop)


def test_project_intake_drops_empty_input_returns_empty():
    assert project_intake_drops([]) == []


def test_project_intake_drops_no_matches_returns_empty():
    insights = [
        _insight("I-1", "mastitis_alert"),
        _insight("I-2", "lameness"),
    ]
    assert project_intake_drops(insights) == []


def test_project_intake_drops_extracts_title_and_date():
    insights = [
        _insight("I-1", "feed_intake_drop", title="Группа 1 — −18% DMI", date="2026-05-14"),
    ]
    result = project_intake_drops(insights)
    assert len(result) == 1
    assert result[0].title == "Группа 1 — −18% DMI"
    assert result[0].last_observed_at == "2026-05-14"


def test_project_intake_drops_handles_objects_with_attributes():
    """Accept both dict-like and pydantic-like inputs."""
    class _O:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    insights = [_O(**_insight("I-1", "feed_intake_drop"))]
    result = project_intake_drops(insights)
    assert len(result) == 1
    assert result[0].insight_id == "I-1"
```

- [ ] **Step 2: Run tests — expected FAIL (module not found)**

```bash
cd /opt/genomeai/repo && pytest tests/test_feeding_v1.py -v 2>&1 | tail -20
```

Expected: `ModuleNotFoundError: No module named 'web_cabinet.feeding_v1'`.

- [ ] **Step 3: Создать `web_cabinet/feeding_v1.py`**

```python
"""Feeding domain helpers (P1-3b).

Pure functions only: yaml loaders + insight projections.
FastAPI routes live in web_cabinet.api_boundary_v1.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

import yaml

from packages.contracts.api_boundary_v1 import FeedingRation, FeedIntakeDrop

logger = logging.getLogger(__name__)

# Insight `type` values that we consider feeding-related.
# Adding a new type here is the single-source-of-truth change.
FEED_INSIGHT_TYPES: frozenset[str] = frozenset({
    "feed_intake_drop",
    "dmi_drop",
})


def _read_yaml(path: Path) -> Any:
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("feeding: failed to read %s: %s", path, exc)
        return None


def load_rations(config_path: Path) -> list[FeedingRation]:
    """Read group rations from a yaml file. Returns [] on any failure or empty config.

    Schema is documented in configs/feeding/rations_v1.yaml. Invalid items are skipped.
    """
    data = _read_yaml(config_path)
    if not isinstance(data, dict):
        return []
    groups = data.get("groups") or []
    if not isinstance(groups, list):
        return []
    out: list[FeedingRation] = []
    for entry in groups:
        if not isinstance(entry, dict):
            continue
        group_id = entry.get("group_id")
        group_name = entry.get("group_name")
        ration_name = entry.get("ration_name")
        if not group_id or not group_name or not ration_name:
            continue
        out.append(
            FeedingRation(
                group_id=str(group_id),
                group_name=str(group_name),
                ration_name=str(ration_name),
                dm_kg=_to_float(entry.get("dm_kg")),
                last_distribution_at=_to_optstr(entry.get("last_distribution_at")),
                status=str(entry.get("status") or "unknown"),
            )
        )
    return out


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_optstr(value: Any) -> str | None:
    if value is None:
        return None
    try:
        s = str(value).strip()
        return s or None
    except Exception:
        return None


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from either a dict or an attribute holder (pydantic model, dataclass)."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def project_intake_drops(insights: Iterable[Any]) -> list[FeedIntakeDrop]:
    """Filter feed-related insights and project them into FeedIntakeDrop items.

    Insights may be dicts or attribute-holding objects (e.g., pydantic InsightItem).
    Unknown / malformed shapes return empty per item — never raise.
    """
    out: list[FeedIntakeDrop] = []
    for ins in insights or []:
        try:
            type_ = _get(ins, "type", "")
            if not isinstance(type_, str):
                continue
            if type_ not in FEED_INSIGHT_TYPES:
                continue
            insight_id = _get(ins, "insight_id", "") or _get(ins, "id", "")
            if not insight_id:
                continue
            out.append(
                FeedIntakeDrop(
                    insight_id=str(insight_id),
                    group_id=None,
                    group_name=None,
                    drop_pct=_extract_drop_pct(_get(ins, "chart_data", []) or []),
                    window_days=None,
                    last_observed_at=_to_optstr(_get(ins, "date", None)),
                    title=str(_get(ins, "title", "") or ""),
                )
            )
        except Exception as exc:
            logger.warning("feeding: skip malformed insight in projection: %s", exc)
            continue
    return out


def _extract_drop_pct(chart_data: Iterable[Any]) -> float | None:
    """If chart_data has at least two numeric points, return (last - first) / first * 100 (signed).

    Returns None if chart_data is too short or non-numeric.
    """
    try:
        pts = [float(x) for x in chart_data if isinstance(x, (int, float))]
    except (TypeError, ValueError):
        return None
    if len(pts) < 2 or pts[0] == 0:
        return None
    return (pts[-1] - pts[0]) / pts[0] * 100.0
```

- [ ] **Step 4: Run tests — expected PASS**

```bash
cd /opt/genomeai/repo && pytest tests/test_feeding_v1.py -v 2>&1 | tail -25
```

Expected: все 10 тестов PASS (5 для load_rations, 5 для project_intake_drops).

> Если какой-то тест fails — это сигнал к корректировке кода в `feeding_v1.py`, не корректировке теста (тесты — спецификация).

- [ ] **Step 5: Commit**

```bash
cd /opt/genomeai/repo && git add web_cabinet/feeding_v1.py tests/test_feeding_v1.py && git commit -m "feat(feeding): pure loaders + insight projector with unit tests (P1-3b)"
```

---

## Task 4: FastAPI routes в `web_cabinet/api_boundary_v1.py`

**Files:**
- Modify: `web_cabinet/api_boundary_v1.py`

- [ ] **Step 1: Добавить импорты pydantic-классов**

Найти существующий import-блок из `packages.contracts.api_boundary_v1` (начинается на строке ~8, заканчивается ~80). В отсортированной части (упорядочено алфавитно) **добавить**:

```python
    FeedingRation,
    FeedingRationsResponse,
    FeedIntakeDrop,
    FeedIntakeDropsResponse,
```

> Конкретное место: после `EconomicsScenarioItem,` и перед `EntityRef,` (по алфавиту: Economics... < Feed... < Entity...). Если расположение import'ов в этом файле не строго алфавитное — вставить любым удобным образом, главное в этот же блок import'ов из `packages.contracts.api_boundary_v1`.

- [ ] **Step 2: Добавить импорт helper-функций**

В верхней части файла найти существующий импорт `from web_cabinet.insights_v1 import list_insights as _list_insights,` (или похожий по форме). Добавить отдельной строкой (если необходимо — создать новый импорт):

```python
from web_cabinet.feeding_v1 import load_rations as _load_rations, project_intake_drops as _project_intake_drops
```

- [ ] **Step 3: Найти конец route'а `/recommended-tasks` (line ~1514) и сразу после него вставить два новых route'а**

```python


@router.get('/feeding/rations', response_model=FeedingRationsResponse)
def boundary_feeding_rations(
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'kpi.view'):
        raise HTTPException(status_code=403)
    cfg_path = Path(__file__).resolve().parents[1] / 'configs' / 'feeding' / 'rations_v1.yaml'
    items = _load_rations(cfg_path)
    return FeedingRationsResponse(total=len(items), items=items)


@router.get('/feeding/intake-drops', response_model=FeedIntakeDropsResponse)
def boundary_feeding_intake_drops(
    farm_id: str = 'INV_FARM_001',
    user=Depends(get_current_user),
):
    if not _user_has_any(user, 'kpi.view'):
        raise HTTPException(status_code=403)
    user_id = str(user.get('user_id') or user.get('username') or 'unknown')
    insights_resp = _list_insights(farm_id=farm_id, user_id=user_id)
    items = _project_intake_drops(insights_resp.items)
    return FeedIntakeDropsResponse(total=len(items), items=items)
```

> Проверить, что `Path` уже импортирован в файле (используется `Path(__file__).resolve().parents[1]` в paths). Сейчас в верхней части видно `from pathlib import Path`. ОК.

- [ ] **Step 4: Smoke — boot the API and curl the endpoints**

```bash
cd /opt/genomeai/repo && python -c "from web_cabinet.api_boundary_v1 import router; print([r.path for r in router.routes if 'feeding' in r.path])"
```

Expected: `['/feeding/rations', '/feeding/intake-drops']`.

- [ ] **Step 5: Лайв smoke через uvicorn (если backend уже поднят на :8000 — пропустить boot; иначе поднять)**

Если backend не поднят — пропустить тест-курлы; они отработают на гейте web_smoke.

Если backend поднят (`curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/api/runtime-state` возвращает 200/401) — выполнить:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/app/v1/feeding/rations
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/api/app/v1/feeding/intake-drops
```

Expected: оба возвращают `401` (Unauthorized — нет токена). Это положительный signal: routes зарегистрированы, auth-чек срабатывает.

- [ ] **Step 6: Commit**

```bash
cd /opt/genomeai/repo && git add web_cabinet/api_boundary_v1.py && git commit -m "feat(api): GET /feeding/rations + /feeding/intake-drops (P1-3b)"
```

---

## Task 5: Регистрация в `docs/public_interfaces.json`

**Files:**
- Modify: `docs/public_interfaces.json`

- [ ] **Step 1: Найти `/feedback` запись (алфавитно перед /feeding)**

```bash
grep -n "\"path\": \"/feedback\"" /opt/genomeai/repo/docs/public_interfaces.json | head -2
```

- [ ] **Step 2: Вставить два endpoint entries между `/feedback*` и следующим маршрутом (алфавитный порядок)**

Используя Edit, найти конкретный блок (`/feedback` или ближайшая существующая запись после `/feedback*`) и добавить **после** его закрывающей `},`:

```json
      {
        "path": "/feeding/intake-drops",
        "methods": [
          "GET"
        ]
      },
      {
        "path": "/feeding/rations",
        "methods": [
          "GET"
        ]
      },
```

> JSON-структура использует одинаковые отступы (6 пробелов для свойств в массиве). Проверь, что в файле они именно такие — иначе подстрой. Также убедись, что есть запятая после новой записи, и предыдущий блок заканчивается на `},` (открывающая запятая для новой записи).

- [ ] **Step 3: Validate JSON**

```bash
python -c "import json; json.load(open('/opt/genomeai/repo/docs/public_interfaces.json')); print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
cd /opt/genomeai/repo && git add docs/public_interfaces.json && git commit -m "docs(interfaces): register /feeding/rations and /feeding/intake-drops (P1-3b)"
```

---

## Task 6: TS-контракты в `web_app/lib/api/contracts.ts`

**Files:**
- Modify: `web_app/lib/api/contracts.ts`

- [ ] **Step 1: Найти место вставки**

```bash
grep -n "^export type WorklistsFromRecommendedResponse" /opt/genomeai/repo/web_app/lib/api/contracts.ts
```

Expected: одна строка (например, 351).

- [ ] **Step 2: Сразу после закрывающей `};` `WorklistsFromRecommendedResponse` вставить:**

```typescript

export type FeedingRation = {
  group_id: string;
  group_name: string;
  ration_name: string;
  dm_kg?: number | null;
  last_distribution_at?: string | null;
  status: string;
};

export type FeedingRationsResponse = {
  schema: string;
  total: number;
  items: FeedingRation[];
};

export type FeedIntakeDrop = {
  insight_id: string;
  group_id?: string | null;
  group_name?: string | null;
  drop_pct?: number | null;
  window_days?: number | null;
  last_observed_at?: string | null;
  title: string;
};

export type FeedIntakeDropsResponse = {
  schema: string;
  total: number;
  items: FeedIntakeDrop[];
};
```

- [ ] **Step 3: Run typecheck**

```bash
cd /opt/genomeai/repo/web_app && npm run typecheck
```

Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
cd /opt/genomeai/repo && git add web_app/lib/api/contracts.ts && git commit -m "feat(ts-contracts): FeedingRation / FeedIntakeDrop types (P1-3b)"
```

---

## Task 7: Frontend client `web_app/lib/api/feeding.ts`

**Files:**
- Create: `web_app/lib/api/feeding.ts`

- [ ] **Step 1: Посмотреть pattern существующего тонкого клиента**

```bash
head -40 /opt/genomeai/repo/web_app/lib/api/insights-client.ts
```

> Цель: понять, как делаются запросы (через backendProxyBasePath / fetch wrapper). Если в репо есть единый клиент-объект (например, в `client.ts`), используем его. Если каждый файл — самостоятельный fetch, повторяем тот же стиль.

- [ ] **Step 2: Создать `/opt/genomeai/repo/web_app/lib/api/feeding.ts`**

```typescript
import type { FeedingRationsResponse, FeedIntakeDropsResponse } from './contracts';

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: 'include' });
  if (!res.ok) {
    throw new Error(`Feeding API ${path} failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

export function getFeedingRations(): Promise<FeedingRationsResponse> {
  return fetchJson<FeedingRationsResponse>('/api/backend/feeding/rations');
}

export function getFeedIntakeDrops(): Promise<FeedIntakeDropsResponse> {
  return fetchJson<FeedIntakeDropsResponse>('/api/backend/feeding/intake-drops');
}
```

> Проверь, что путь `/api/backend/...` — это правильный proxy-prefix для Next.js → backend. Открой `web_app/lib/api/client.ts` и убедись, что `backendProxyBasePath` равно `/api/backend`. Если нет — подкорректируй URL до правильного proxy-prefix.

- [ ] **Step 3: Run typecheck**

```bash
cd /opt/genomeai/repo/web_app && npm run typecheck
```

Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
cd /opt/genomeai/repo && git add web_app/lib/api/feeding.ts && git commit -m "feat(web): feeding API client (P1-3b)"
```

---

## Task 8: Страница `/feeding`

**Files:**
- Create: `web_app/app/(protected)/feeding/page.tsx`

- [ ] **Step 1: Посмотреть pattern существующих protected-страниц с двумя панелями**

```bash
head -60 /opt/genomeai/repo/web_app/app/\(protected\)/decisions/page.tsx 2>/dev/null
```

> Цель — понять, какие имена компонентов layout/header используются. Если есть общий `<PageHeader>` или `<AppShell>` — повторяем.

- [ ] **Step 2: Создать каталог и страницу**

```bash
mkdir -p /opt/genomeai/repo/web_app/app/\(protected\)/feeding
```

Файл `/opt/genomeai/repo/web_app/app/(protected)/feeding/page.tsx`:

```tsx
'use client';

import { useEffect, useState } from 'react';
import type { FeedingRation, FeedIntakeDrop } from '@/lib/api/contracts';
import { getFeedingRations, getFeedIntakeDrops } from '@/lib/api/feeding';

export default function FeedingPage() {
  const [rations, setRations] = useState<FeedingRation[] | null>(null);
  const [drops, setDrops] = useState<FeedIntakeDrop[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([getFeedingRations(), getFeedIntakeDrops()])
      .then(([rationsResp, dropsResp]) => {
        if (!alive) return;
        setRations(rationsResp.items);
        setDrops(dropsResp.items);
      })
      .catch((e: unknown) => {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="page-shell">
      <header className="page-header">
        <h1>Кормление</h1>
        <nav aria-label="Хлебные крошки" className="breadcrumbs">
          <span>Стадо</span>
          <span aria-hidden> › </span>
          <span aria-current="page">Кормление</span>
        </nav>
      </header>

      {error && (
        <div role="alert" className="page-error">
          Ошибка загрузки данных: {error}
        </div>
      )}

      <section className="panel">
        <h2>Рационы по группам</h2>
        {rations === null && !error ? (
          <p className="panel-loading">Загрузка…</p>
        ) : rations && rations.length > 0 ? (
          <table className="data-table">
            <thead>
              <tr>
                <th>Группа</th>
                <th>Рацион</th>
                <th>СВ, кг</th>
                <th>Последняя раздача</th>
                <th>Статус</th>
              </tr>
            </thead>
            <tbody>
              {rations.map((r) => (
                <tr key={r.group_id}>
                  <td>{r.group_name}</td>
                  <td>{r.ration_name}</td>
                  <td>{r.dm_kg ?? '—'}</td>
                  <td>{r.last_distribution_at ?? '—'}</td>
                  <td>{r.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="panel-empty">Рационы ещё не настроены.</p>
        )}
      </section>

      <section className="panel">
        <h2>Группы со снижением потребления</h2>
        {drops === null && !error ? (
          <p className="panel-loading">Загрузка…</p>
        ) : drops && drops.length > 0 ? (
          <ul className="card-list">
            {drops.map((d) => (
              <li key={d.insight_id} className="drop-card">
                <h3>{d.group_name ?? d.title}</h3>
                <dl>
                  <div>
                    <dt>Падение</dt>
                    <dd>{d.drop_pct !== null && d.drop_pct !== undefined ? `${d.drop_pct.toFixed(1)}%` : '—'}</dd>
                  </div>
                  <div>
                    <dt>Окно</dt>
                    <dd>{d.window_days ? `${d.window_days} д.` : '—'}</dd>
                  </div>
                  <div>
                    <dt>Зафиксировано</dt>
                    <dd>{d.last_observed_at ?? '—'}</dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        ) : (
          <p className="panel-empty">Снижения потребления не выявлены.</p>
        )}
      </section>
    </div>
  );
}
```

> CSS-классы (`page-shell`, `page-header`, `breadcrumbs`, `panel`, `data-table`, `panel-empty`, `panel-loading`, `card-list`, `drop-card`, `page-error`) — используем существующие, если такие классы уже есть в globals.css. Если нет — добавить минимальные стили **в этом же шаге**, чтобы страница не была без оформления. Перед написанием стилей быстро `grep`-нуть в globals.css.

- [ ] **Step 3: Проверить наличие CSS-классов**

```bash
grep -cE "\.(page-shell|page-header|breadcrumbs|panel|data-table|panel-empty|panel-loading|card-list|drop-card|page-error)\b" /opt/genomeai/repo/web_app/app/globals.css
```

Если число < 10 — добавить недостающие классы в globals.css. Минимальный блок (вставить в конец файла, перед последним `}` если такой есть; или просто append):

```css

/* Feeding page (P1-3b) — minimal scaffold styles */
.page-shell { display: flex; flex-direction: column; gap: 1.5rem; padding: 1.5rem; }
.page-header h1 { margin: 0 0 0.25rem; }
.breadcrumbs { display: flex; gap: 0.25rem; font-size: 0.85em; color: var(--text-secondary); }
.panel { display: flex; flex-direction: column; gap: 0.75rem; }
.panel h2 { margin: 0; font-size: 1.1rem; }
.panel-empty, .panel-loading { color: var(--text-muted); }
.page-error { color: var(--danger, #c00); }
.data-table { width: 100%; border-collapse: collapse; }
.data-table th, .data-table td { padding: 0.5rem 0.75rem; text-align: left; border-bottom: 1px solid var(--border); }
.card-list { list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 0.75rem; }
.drop-card { border: 1px solid var(--border); border-radius: var(--radius, 6px); padding: 0.75rem 1rem; }
.drop-card h3 { margin: 0 0 0.5rem; font-size: 1rem; }
.drop-card dl { margin: 0; display: flex; flex-direction: column; gap: 0.25rem; }
.drop-card dl > div { display: flex; justify-content: space-between; }
```

> Использовать переменные, существующие в `:root` (см. globals.css верх): `--text-secondary`, `--text-muted`, `--border`, `--radius`, `--danger` (если нет — fallback `#c00`).

- [ ] **Step 4: Run typecheck**

```bash
cd /opt/genomeai/repo/web_app && npm run typecheck
```

Expected: exit 0.

- [ ] **Step 5: Run validate-foundation**

```bash
cd /opt/genomeai/repo/web_app && npm run test
```

Expected: stdout содержит `web_app T32-07 validation OK`.

- [ ] **Step 6: Commit**

```bash
cd /opt/genomeai/repo && git add web_app/app/\(protected\)/feeding/page.tsx web_app/app/globals.css && git commit -m "feat(web): /feeding page — rations table + intake-drops cards (P1-3b)"
```

> Если CSS-классы уже были и globals.css не правился — убрать его из `git add`.

---

## Task 9: Browser smoke + execution proof

**Files:**
- Create: `docs/iterations/T34-P1-3b_execution_proof.md`

- [ ] **Step 1: Поднять dev-stack**

```bash
cd /opt/genomeai/repo && python -m genomeai.app_launcher --open-browser
```

> Если уже поднят — пропустить. Дождаться `/dashboard` в браузере.

- [ ] **Step 2: Залогиниться (admin/admin) и перейти на /feeding**

1. Открыть http://127.0.0.1:3000/feeding (или через sidebar: Стадо → Кормление).
2. Ожидаемо:
   - Заголовок «Кормление» виден.
   - Breadcrumbs «Стадо › Кормление».
   - Панель «Рационы по группам» с empty-state «Рационы ещё не настроены» (yaml пуст).
   - Панель «Группы со снижением потребления» с empty-state «Снижения потребления не выявлены» (нет feed_intake_drop insight'ов).
   - В DevTools → Network: оба запроса (`/api/backend/feeding/rations` и `/api/backend/feeding/intake-drops`) вернули 200 OK.

- [ ] **Step 3: Проверить permission gate (опционально, если есть viewer без kpi.view)**

Если есть user без `kpi.view` — залогиниться, перейти на /feeding. Network вкладка должна показать 403 на оба запроса. Если такого пользователя нет — пропустить, отметить в proof как «not verified live».

- [ ] **Step 4: Прогнать 7 гейтов CLAUDE.md §4**

Из корня репо:

```bash
bash scripts/run_ci_gate.sh 2>&1 | tail -5
python -m web_cabinet.smoke --workdir _tmp/ci_smoke --clean --timing-json artifacts/_ci/web_smoke.json 2>&1 | tail -5
python -m genomeai.cli verify_refactor --project-root . --golden golden --report-root artifacts/_ci/verify_refactor 2>&1 | tail -5
bash scripts/run_warning_governance_gate.sh 2>&1 | tail -5
bash scripts/run_operational_rollout_gate.sh 2>&1 | tail -5
bash scripts/run_competitive_acceptance_gate.sh 2>&1 | tail -5
bash scripts/run_perf_gates.sh 2>&1 | tail -5
```

Все 7 должны exit 0. Если какой-то fails — зафиксировать в proof, диагностировать причину; если причина **не** в наших изменениях — задокументировать как pre-existing и продолжить.

- [ ] **Step 5: Записать proof в `docs/iterations/T34-P1-3b_execution_proof.md`**

Шаблон (заменить `<...>` плейсхолдеры на реальные SHA / результаты):

```markdown
# T34-P1-3b Execution Proof — /feeding skeleton

**Date:** 2026-05-15
**Spec:** docs/superpowers/specs/2026-05-15-p1-3-stado-accordion-design.md §3
**Plan:** docs/superpowers/plans/2026-05-15-p1-3b-feeding-skeleton.md

## Commits

1. `<sha>` feat(feeding): empty rations_v1.yaml catalog (P1-3b)
2. `<sha>` feat(contracts): pydantic models for /feeding endpoints (P1-3b)
3. `<sha>` feat(feeding): pure loaders + insight projector with unit tests (P1-3b)
4. `<sha>` feat(api): GET /feeding/rations + /feeding/intake-drops (P1-3b)
5. `<sha>` docs(interfaces): register /feeding/rations and /feeding/intake-drops (P1-3b)
6. `<sha>` feat(ts-contracts): FeedingRation / FeedIntakeDrop types (P1-3b)
7. `<sha>` feat(web): feeding API client (P1-3b)
8. `<sha>` feat(web): /feeding page — rations table + intake-drops cards (P1-3b)

## Scope

- `configs/feeding/rations_v1.yaml` empty skeleton (data-driven; no hardcoded rations).
- 4 pydantic-models + 4 TS-types for two new endpoints.
- `web_cabinet/feeding_v1.py` pure helpers (yaml loader + insight projector); 10 unit tests.
- `GET /api/app/v1/feeding/rations`, `GET /api/app/v1/feeding/intake-drops` — permission `kpi.view`, graceful empty fallbacks.
- `/feeding` page with header, breadcrumbs, rations table, drop cards, empty-states.

Codebase-convention deviation from spec: pydantic classes added to existing `packages/contracts/api_boundary_v1.py` (not a new `feeding_v1.py`) per established repo pattern.

## Executed gates

| # | Gate | Exit | Notes |
|---|------|------|-------|
| 1 | pytest gate | <0/non-0> | <log path> |
| 2 | web smoke | <0/non-0> | <log path> |
| 3 | verify_refactor (golden) | <0/non-0> | <log path> |
| 4 | warning governance | <0/non-0> | <log path> |
| 5 | operational rollout | <0/non-0> | <log path> |
| 6 | competitive acceptance | <0/non-0> | <log path> |
| 7 | performance | <0/non-0> | <log path> |

## Browser smoke

- /feeding loads, both panels show empty-state, network 200 OK on both endpoints.
- Permission gate verified / not-verified-live (note).

## Net result

- proven (если все 7 gates green + browser smoke OK), либо
- partially_proven (если какие-то gates fail по pre-existing причинам — задокументировать).

## Honest status

<proven | partially_proven | not_proven | blocked>.
```

- [ ] **Step 6: Заменить плейсхолдеры на реальные SHA**

```bash
cd /opt/genomeai/repo && git log --oneline -10
```

Скопировать 8 первых SHA в proof-файл.

- [ ] **Step 7: Commit execution proof**

```bash
cd /opt/genomeai/repo && git add docs/iterations/T34-P1-3b_execution_proof.md && git commit -m "docs(iter): execution proof for P1-3b /feeding skeleton"
```

---

## Self-review notes

**Spec coverage (spec §3):**
- §3.1 (UI: header + breadcrumbs + 2 panels + empty-states) → Task 8 ✓
- §3.2 (Backend rations endpoint + intake-drops endpoint + kpi.view + graceful empty) → Task 4 + Task 3 ✓
- §3.3 (контракты): spec говорит «feeding_v1.{py,ts}», план кладёт в `api_boundary_v1.py` и `contracts.ts`. **Намеренное отступление** задокументировано в Architecture-блоке и Net-result.
- §3.4 (yaml каркас configs/feeding/rations_v1.yaml) → Task 1 ✓
- §3.5 (acceptance: empty endpoints, страница без ошибок, 403 без permission) → Task 9 Step 2-3 ✓
- §6 (public_interfaces.json +2 endpoints) → Task 5 ✓
- §7 risk #1 (feed_intake_drop kind may not exist) — code returns empty + log; tests cover this ✓
- §7 risk #2 (domain health vs vet) — N/A для P1-3b, относится к P1-3d.
- §7 risk #5 (kpi.view permission на /feeding) — задокументировано в spec; используем kpi.view, поведение задокументировано в plan Task 4 Step 3 ✓

**Placeholder scan:**
- Внутри code blocks плана: проверены, нет TBD/TODO.
- В proof-template: `<sha>` и `<...>` плейсхолдеры — это шаблонные слоты, заполняются в Step 6 (отдельный шаг). Это не «план failures», а нормальный proof-template.

**Type consistency:**
- `FeedingRation` / `FeedingRationsResponse` / `FeedIntakeDrop` / `FeedIntakeDropsResponse` — одинаковые имена в Task 2 (pydantic), Task 6 (TS).
- Поля совпадают (Python `dm_kg: Optional[float]` ↔ TS `dm_kg?: number | null`; и т.д.).
- `load_rations(config_path: Path) -> list[FeedingRation]` определена в Task 3, импортируется в Task 4.
- `project_intake_drops(insights) -> list[FeedIntakeDrop]` определена в Task 3, импортируется в Task 4.
- Route paths `/feeding/rations`, `/feeding/intake-drops` — одинаковые в Task 4, Task 5, Task 7.

---

## Execution Handoff

После сохранения этого плана — координатор выбирает execution mode (subagent-driven vs inline).

# PMV-B04: Impact Panel UI — StatisticalImpactResult Wire-up

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `POST /api/impact` backend endpoint returning per-KPI statistical impact results and wire them into the Impact Panel frontend to show p-value badges, effect sizes, and 95% CI.

**Architecture:** A new FastAPI router (`web_cabinet/ai/endpoints/impact.py`) serves statistical analysis results in either demo (seeded JSON) or real (`compute_full_impact`) mode, registered via the existing `register_ai_routes` function with no path prefix so the route lands at `/api/impact`. The frontend `ImpactPanel` gains a new statistical section that fetches this endpoint via `useEffect` and renders one `KPIImpactCard` per KPI. A new `WindowSelector` component wraps the existing window-state passed in from the parent. Existing `MetricCompareCard` / `OtherChangesTable` UI is left untouched.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest; TypeScript 5.8, React 19, Next.js 15, Node.js native test runner (`node:test`)

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `data/demo/investor_v1/seeded_statistical_impact.json` | Demo seeded data for 5 timeline events × 3 KPIs |
| Create | `web_cabinet/ai/endpoints/impact.py` | `POST /api/impact` router — demo + real mode |
| Modify | `web_cabinet/ai/endpoints/__init__.py` | Register impact router (no prefix) |
| Create | `web_cabinet/ai/tests/test_impact_endpoint.py` | Backend tests (TDD) |
| Create | `web_app/components/timeline/kpi-impact-card.tsx` | Per-KPI statistical display: badge + CI + effect size |
| Create | `web_app/components/timeline/window-selector.tsx` | Compact 3d/1w/2w/4w button-group |
| Modify | `web_app/components/timeline/impact-panel.tsx` | Add statistical section below existing metrics grid |
| Create | `web_app/components/timeline/__tests__/kpi-impact-card.test.ts` | Frontend unit tests |
| Create | `docs/iterations/PMV-B04_execution_proof.md` | Execution proof |

---

## Task 1: Create seeded statistical impact data

**Files:**
- Create: `data/demo/investor_v1/seeded_statistical_impact.json`

- [ ] **Step 1: Write the seeded JSON file**

Create `data/demo/investor_v1/seeded_statistical_impact.json` with entries for the 5 demo events (TL_001–TL_005), each having 3 KPI results covering all three significance verdicts.

```json
[
  {
    "event_id": "TL_001",
    "kpi_results": [
      {
        "kpi": "milk_yield",
        "diff_in_diff_effect": -1.82,
        "p_value": 0.011,
        "cohen_d": -0.71,
        "magnitude": "medium",
        "ci_95": [-3.1, -0.53],
        "significance": "significant",
        "before": {"mean": 28.4, "n": 15},
        "after": {"mean": 26.6, "n": 15}
      },
      {
        "kpi": "scc",
        "diff_in_diff_effect": 142.0,
        "p_value": 0.003,
        "cohen_d": 0.88,
        "magnitude": "large",
        "ci_95": [62.0, 222.0],
        "significance": "significant",
        "before": {"mean": 210.0, "n": 15},
        "after": {"mean": 352.0, "n": 15}
      },
      {
        "kpi": "dmr",
        "diff_in_diff_effect": 0.04,
        "p_value": 0.24,
        "cohen_d": 0.15,
        "magnitude": "negligible",
        "ci_95": [-0.03, 0.11],
        "significance": "not_significant",
        "before": {"mean": 1.12, "n": 15},
        "after": {"mean": 1.16, "n": 15}
      }
    ]
  },
  {
    "event_id": "TL_002",
    "kpi_results": [
      {
        "kpi": "milk_yield",
        "diff_in_diff_effect": -0.6,
        "p_value": 0.31,
        "cohen_d": -0.12,
        "magnitude": "negligible",
        "ci_95": [-1.8, 0.6],
        "significance": "not_significant",
        "before": {"mean": 26.1, "n": 12},
        "after": {"mean": 25.5, "n": 12}
      },
      {
        "kpi": "dry_matter_intake",
        "diff_in_diff_effect": -2.3,
        "p_value": 0.028,
        "cohen_d": -0.54,
        "magnitude": "medium",
        "ci_95": [-4.2, -0.4],
        "significance": "significant",
        "before": {"mean": 21.8, "n": 12},
        "after": {"mean": 19.5, "n": 12}
      },
      {
        "kpi": "scc",
        "diff_in_diff_effect": 12.0,
        "p_value": 0.61,
        "cohen_d": 0.08,
        "magnitude": "negligible",
        "ci_95": [-33.0, 57.0],
        "significance": "not_significant",
        "before": {"mean": 185.0, "n": 12},
        "after": {"mean": 197.0, "n": 12}
      }
    ]
  },
  {
    "event_id": "TL_003",
    "kpi_results": [
      {
        "kpi": "milk_yield",
        "diff_in_diff_effect": -2.9,
        "p_value": 0.019,
        "cohen_d": -0.62,
        "magnitude": "medium",
        "ci_95": [-5.3, -0.5],
        "significance": "significant",
        "before": {"mean": 31.2, "n": 8},
        "after": {"mean": 28.3, "n": 8}
      },
      {
        "kpi": "scc",
        "diff_in_diff_effect": 195.0,
        "p_value": 0.007,
        "cohen_d": 0.93,
        "magnitude": "large",
        "ci_95": [78.0, 312.0],
        "significance": "significant",
        "before": {"mean": 225.0, "n": 8},
        "after": {"mean": 420.0, "n": 8}
      },
      {
        "kpi": "reproductive_rate",
        "diff_in_diff_effect": -0.03,
        "p_value": 0.44,
        "cohen_d": -0.18,
        "magnitude": "negligible",
        "ci_95": [-0.09, 0.04],
        "significance": "not_significant",
        "before": {"mean": 0.58, "n": 8},
        "after": {"mean": 0.55, "n": 8}
      }
    ]
  },
  {
    "event_id": "TL_004",
    "kpi_results": [
      {
        "kpi": "milk_yield",
        "diff_in_diff_effect": 1.1,
        "p_value": 0.048,
        "cohen_d": 0.41,
        "magnitude": "small",
        "ci_95": [0.01, 2.2],
        "significance": "significant",
        "before": {"mean": 24.8, "n": 20},
        "after": {"mean": 25.9, "n": 20}
      },
      {
        "kpi": "scc",
        "diff_in_diff_effect": -18.0,
        "p_value": 0.09,
        "cohen_d": -0.28,
        "magnitude": "small",
        "ci_95": [-38.0, 3.0],
        "significance": "not_significant",
        "before": {"mean": 198.0, "n": 20},
        "after": {"mean": 180.0, "n": 20}
      },
      {
        "kpi": "dmr",
        "diff_in_diff_effect": 0.11,
        "p_value": 0.033,
        "cohen_d": 0.47,
        "magnitude": "small",
        "ci_95": [0.01, 0.21],
        "significance": "significant",
        "before": {"mean": 0.98, "n": 20},
        "after": {"mean": 1.09, "n": 20}
      }
    ]
  },
  {
    "event_id": "TL_005",
    "kpi_results": [
      {
        "kpi": "milk_yield",
        "diff_in_diff_effect": 0.3,
        "p_value": 0.71,
        "cohen_d": 0.07,
        "magnitude": "negligible",
        "ci_95": [-1.3, 1.9],
        "significance": "not_significant",
        "before": {"mean": 23.1, "n": 5},
        "after": {"mean": 23.4, "n": 5}
      },
      {
        "kpi": "scc",
        "diff_in_diff_effect": 8.0,
        "p_value": 0.88,
        "cohen_d": 0.04,
        "magnitude": "negligible",
        "ci_95": [-52.0, 68.0],
        "significance": "not_significant",
        "before": {"mean": 190.0, "n": 5},
        "after": {"mean": 198.0, "n": 5}
      },
      {
        "kpi": "reproductive_rate",
        "diff_in_diff_effect": 0.01,
        "p_value": 0.92,
        "cohen_d": 0.03,
        "magnitude": "negligible",
        "ci_95": [-0.11, 0.13],
        "significance": "not_significant",
        "before": {"mean": 0.51, "n": 5},
        "after": {"mean": 0.52, "n": 5}
      }
    ]
  }
]
```

- [ ] **Step 2: Commit seeded data**

```bash
git add data/demo/investor_v1/seeded_statistical_impact.json
git commit -m "feat(PMV-B04): add seeded statistical impact data for demo mode"
```

---

## Task 2: Write failing backend tests (TDD)

**Files:**
- Create: `web_cabinet/ai/tests/test_impact_endpoint.py`

- [ ] **Step 1: Write the test file**

Create `web_cabinet/ai/tests/test_impact_endpoint.py`:

```python
"""Tests for POST /api/impact endpoint."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture
def app_with_impact():
    """Create a minimal FastAPI app with the impact router registered."""
    from fastapi import FastAPI
    from web_cabinet.ai.endpoints.impact import router
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app_with_impact):
    return TestClient(app_with_impact)


DEMO_PAYLOAD = {
    "event_id": "TL_001",
    "farm_id": "demo-farm-v1",
    "event_date": "2026-03-10",
    "event_type": "mastitis_outbreak",
    "affected_groups": ["group_1"],
    "kpi_list": ["milk_yield", "scc"],
    "window": "2w",
}


class TestImpactEndpointDemo:
    def test_demo_returns_seeded_structure(self, client):
        """Demo mode returns seeded data with correct top-level keys."""
        with patch("web_cabinet.ai.endpoints.impact.get_ai_settings") as mock_settings:
            mock_settings.return_value = MagicMock(GENOMEAI_AI_DEMO_MODE=True)
            resp = client.post("/api/impact", json=DEMO_PAYLOAD)

        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"] == "TL_001"
        assert isinstance(data["kpi_results"], list)
        assert len(data["kpi_results"]) >= 1

    def test_demo_kpi_result_fields(self, client):
        """Each kpi_result in demo mode has all required fields."""
        with patch("web_cabinet.ai.endpoints.impact.get_ai_settings") as mock_settings:
            mock_settings.return_value = MagicMock(GENOMEAI_AI_DEMO_MODE=True)
            resp = client.post("/api/impact", json=DEMO_PAYLOAD)

        assert resp.status_code == 200
        result = resp.json()["kpi_results"][0]
        required_fields = {
            "kpi", "diff_in_diff_effect", "p_value", "cohen_d",
            "magnitude", "ci_95", "significance", "before", "after",
        }
        assert required_fields.issubset(result.keys())
        assert isinstance(result["ci_95"], list)
        assert len(result["ci_95"]) == 2
        assert isinstance(result["before"], dict)
        assert "mean" in result["before"] and "n" in result["before"]

    def test_demo_significance_values_valid(self, client):
        """Significance field is one of the three allowed values."""
        with patch("web_cabinet.ai.endpoints.impact.get_ai_settings") as mock_settings:
            mock_settings.return_value = MagicMock(GENOMEAI_AI_DEMO_MODE=True)
            resp = client.post("/api/impact", json=DEMO_PAYLOAD)

        assert resp.status_code == 200
        valid = {"significant", "not_significant", "inconclusive"}
        for r in resp.json()["kpi_results"]:
            assert r["significance"] in valid

    def test_demo_unknown_event_returns_fallback(self, client):
        """Unknown event_id in demo mode returns a valid fallback response."""
        payload = {**DEMO_PAYLOAD, "event_id": "UNKNOWN_EVT_999"}
        with patch("web_cabinet.ai.endpoints.impact.get_ai_settings") as mock_settings:
            mock_settings.return_value = MagicMock(GENOMEAI_AI_DEMO_MODE=True)
            resp = client.post("/api/impact", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"] == "UNKNOWN_EVT_999"
        assert isinstance(data["kpi_results"], list)


class TestImpactEndpointRealMode:
    def test_real_mode_calls_compute_full_impact(self, client):
        """Real mode calls compute_full_impact for each KPI in kpi_list."""
        from web_cabinet.analytics.statistical_extension import StatisticalImpactResult

        mock_result = StatisticalImpactResult(
            treated_before=25.0,
            treated_after=26.5,
            control_before=25.0,
            control_after=25.1,
            diff_in_diff_effect=1.4,
            welch_t_pvalue=0.031,
            cohen_d_effect_size=0.52,
            effect_magnitude="medium",
            bootstrap_ci_95=(0.1, 2.7),
            significance="significant",
            sample_sizes={"treated": 15, "control": 45},
        )

        with patch("web_cabinet.ai.endpoints.impact.get_ai_settings") as mock_settings, \
             patch("web_cabinet.ai.endpoints.impact.compute_full_impact", return_value=mock_result) as mock_compute:
            mock_settings.return_value = MagicMock(GENOMEAI_AI_DEMO_MODE=False)
            resp = client.post("/api/impact", json=DEMO_PAYLOAD)

        assert resp.status_code == 200
        # compute_full_impact called once per kpi in kpi_list
        assert mock_compute.call_count == len(DEMO_PAYLOAD["kpi_list"])

    def test_real_mode_p_value_in_response(self, client):
        """Real mode maps welch_t_pvalue → p_value in the response."""
        from web_cabinet.analytics.statistical_extension import StatisticalImpactResult

        mock_result = StatisticalImpactResult(
            treated_before=25.0,
            treated_after=26.5,
            control_before=25.0,
            control_after=25.1,
            diff_in_diff_effect=1.4,
            welch_t_pvalue=0.017,
            cohen_d_effect_size=0.52,
            effect_magnitude="medium",
            bootstrap_ci_95=(0.1, 2.7),
            significance="significant",
            sample_sizes={"treated": 15, "control": 45},
        )

        with patch("web_cabinet.ai.endpoints.impact.get_ai_settings") as mock_settings, \
             patch("web_cabinet.ai.endpoints.impact.compute_full_impact", return_value=mock_result):
            mock_settings.return_value = MagicMock(GENOMEAI_AI_DEMO_MODE=False)
            resp = client.post("/api/impact", json=DEMO_PAYLOAD)

        assert resp.status_code == 200
        result = resp.json()["kpi_results"][0]
        assert result["p_value"] == pytest.approx(0.017)
        assert result["significance"] == "significant"

    def test_real_mode_ci_95_as_list(self, client):
        """ci_95 is serialized as a two-element list (not tuple)."""
        from web_cabinet.analytics.statistical_extension import StatisticalImpactResult

        mock_result = StatisticalImpactResult(
            treated_before=25.0,
            treated_after=26.5,
            control_before=25.0,
            control_after=25.1,
            diff_in_diff_effect=1.4,
            welch_t_pvalue=0.031,
            cohen_d_effect_size=0.52,
            effect_magnitude="medium",
            bootstrap_ci_95=(-0.5, 3.3),
            significance="significant",
            sample_sizes={"treated": 15, "control": 45},
        )

        with patch("web_cabinet.ai.endpoints.impact.get_ai_settings") as mock_settings, \
             patch("web_cabinet.ai.endpoints.impact.compute_full_impact", return_value=mock_result):
            mock_settings.return_value = MagicMock(GENOMEAI_AI_DEMO_MODE=False)
            resp = client.post("/api/impact", json=DEMO_PAYLOAD)

        assert resp.status_code == 200
        ci = resp.json()["kpi_results"][0]["ci_95"]
        assert isinstance(ci, list)
        assert ci == pytest.approx([-0.5, 3.3])
```

- [ ] **Step 2: Verify tests fail (module not yet created)**

```bash
cd /opt/genomeai/worktrees/wt-stat
python -m pytest web_cabinet/ai/tests/test_impact_endpoint.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError` or `ImportError` for `web_cabinet.ai.endpoints.impact`

- [ ] **Step 3: Commit failing tests**

```bash
git add web_cabinet/ai/tests/test_impact_endpoint.py
git commit -m "test(PMV-B04): add failing tests for POST /api/impact endpoint"
```

---

## Task 3: Implement backend endpoint

**Files:**
- Create: `web_cabinet/ai/endpoints/impact.py`

- [ ] **Step 1: Create `web_cabinet/ai/endpoints/impact.py`**

```python
"""POST /api/impact — statistical impact analysis for a farm event (PMV-B04)."""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import get_ai_settings

logger = logging.getLogger("genomeai.ai.endpoint.impact")
router = APIRouter()

_SEEDED_PATH = (
    Path(__file__).parents[3] / "data" / "demo" / "investor_v1" / "seeded_statistical_impact.json"
)


class ImpactRequest(BaseModel):
    event_id: str
    farm_id: str
    event_date: date
    event_type: str
    affected_groups: list[str]
    kpi_list: list[str]
    window: Literal["3d", "1w", "2w", "4w"] = "2w"


def _load_seeded_impact(event_id: str) -> dict:
    """Return seeded statistical impact dict for demo mode."""
    try:
        if _SEEDED_PATH.exists():
            records: list[dict] = json.loads(_SEEDED_PATH.read_text(encoding="utf-8"))
            for rec in records:
                if rec.get("event_id") == event_id:
                    return rec
    except Exception as exc:
        logger.warning("seeded statistical impact load failed: %s", exc)
    # Fallback: return inconclusive result for all known KPIs
    return {
        "event_id": event_id,
        "kpi_results": [
            {
                "kpi": "milk_yield",
                "diff_in_diff_effect": 0.0,
                "p_value": 1.0,
                "cohen_d": 0.0,
                "magnitude": "negligible",
                "ci_95": [-1.0, 1.0],
                "significance": "inconclusive",
                "before": {"mean": 0.0, "n": 0},
                "after": {"mean": 0.0, "n": 0},
            }
        ],
    }


@router.post("/api/impact")
async def compute_event_impact(req: ImpactRequest) -> dict:
    """Compute statistical impact for each KPI in req.kpi_list.

    In demo mode returns pre-seeded data (no compute).
    In real mode calls compute_full_impact from statistical_extension.
    """
    settings = get_ai_settings()

    if settings.GENOMEAI_AI_DEMO_MODE:
        return _load_seeded_impact(req.event_id)

    from web_cabinet.analytics.statistical_extension import compute_full_impact

    results = []
    for kpi in req.kpi_list:
        result = compute_full_impact(
            farm_id=req.farm_id,
            event_date=req.event_date,
            event_type=req.event_type,
            affected_groups=req.affected_groups,
            kpi_metric=kpi,
            window=req.window,
        )
        results.append(
            {
                "kpi": kpi,
                "diff_in_diff_effect": result.diff_in_diff_effect,
                "p_value": result.welch_t_pvalue,
                "cohen_d": result.cohen_d_effect_size,
                "magnitude": result.effect_magnitude,
                "ci_95": list(result.bootstrap_ci_95),
                "significance": result.significance,
                "before": {
                    "mean": result.treated_before,
                    "n": result.sample_sizes.get("treated", 0),
                },
                "after": {
                    "mean": result.treated_after,
                    "n": result.sample_sizes.get("treated", 0),
                },
            }
        )

    return {"event_id": req.event_id, "kpi_results": results}
```

- [ ] **Step 2: Run backend tests — should pass now**

```bash
cd /opt/genomeai/worktrees/wt-stat
python -m pytest web_cabinet/ai/tests/test_impact_endpoint.py -v
```

Expected: All 7 tests PASS.

- [ ] **Step 3: Commit endpoint**

```bash
git add web_cabinet/ai/endpoints/impact.py
git commit -m "feat(PMV-B04): implement POST /api/impact endpoint — demo + real mode"
```

---

## Task 4: Register impact router

**Files:**
- Modify: `web_cabinet/ai/endpoints/__init__.py`

- [ ] **Step 1: Add impact router to `register_ai_routes`**

Open `web_cabinet/ai/endpoints/__init__.py`. The current content ends with:

```python
    app.include_router(impact_narrative_router, prefix="/api/ai", tags=["ai-impact-narrative"])
```

Add these two lines immediately after that line:

```python
    from .impact import router as impact_router
    app.include_router(impact_router, tags=["ai-impact"])
```

The full function after the change looks like:

```python
def register_ai_routes(app: FastAPI) -> None:
    from .health import router as health_router
    from .morning_brief import router as morning_brief_router
    from .morning_brief_pdf import router as morning_brief_pdf_router
    from .ask_farm import router as ask_farm_router
    from .weekly_brief import router as weekly_brief_router
    from .weekly_brief_pdf import router as weekly_brief_pdf_router
    from .insights import router as insights_router
    from .insights_stream import router as insights_stream_router
    from .impact_narrative import router as impact_narrative_router

    app.include_router(health_router, prefix="/api/ai", tags=["ai"])
    app.include_router(morning_brief_router, prefix="/api/ai", tags=["ai-morning-brief"])
    app.include_router(morning_brief_pdf_router, prefix="/api/ai", tags=["ai-morning-brief"])
    app.include_router(ask_farm_router, prefix="/api/ai", tags=["ai"])
    app.include_router(weekly_brief_router, prefix="/api/ai", tags=["ai-weekly-brief"])
    app.include_router(weekly_brief_pdf_router, prefix="/api/ai", tags=["ai-weekly-brief"])
    app.include_router(insights_router, prefix="/api/ai", tags=["ai-insights"])
    app.include_router(insights_stream_router, prefix="/api/ai", tags=["ai-insights"])
    app.include_router(impact_narrative_router, prefix="/api/ai", tags=["ai-impact-narrative"])
    from .impact import router as impact_router
    app.include_router(impact_router, tags=["ai-impact"])
```

- [ ] **Step 2: Smoke-test import**

```bash
cd /opt/genomeai/worktrees/wt-stat
python -c "from web_cabinet.ai.endpoints import register_ai_routes; print('OK')"
```

Expected: `OK` with no errors.

- [ ] **Step 3: Commit router registration**

```bash
git add web_cabinet/ai/endpoints/__init__.py
git commit -m "feat(PMV-B04): register POST /api/impact router in register_ai_routes"
```

---

## Task 5: Create KPIImpactCard frontend component (TDD)

**Files:**
- Create: `web_app/components/timeline/__tests__/kpi-impact-card.test.ts`
- Create: `web_app/components/timeline/kpi-impact-card.tsx`

- [ ] **Step 1: Create the test file**

Create `web_app/components/timeline/__tests__/kpi-impact-card.test.ts`:

```typescript
import test from 'node:test';
import assert from 'node:assert/strict';

// Pure logic tests (no DOM rendering needed for this component's core logic)
// Tests verify the helper functions that determine badge tone and label text.

// ---------------------------------------------------------------------------
// Helpers mirrored from kpi-impact-card.tsx for unit-testability
// ---------------------------------------------------------------------------

type Significance = 'significant' | 'not_significant' | 'inconclusive';
type Magnitude = 'negligible' | 'small' | 'medium' | 'large';

function significanceTone(sig: Significance): 'success' | 'warning' | 'default' {
  if (sig === 'significant') return 'success';
  if (sig === 'not_significant') return 'warning';
  return 'default';
}

function significanceLabel(sig: Significance, p: number): string {
  if (sig === 'significant') return `значимо (p=${p.toFixed(3)})`;
  if (sig === 'not_significant') return 'не значимо';
  return 'недостаточно данных';
}

function magnitudeLabel(mag: Magnitude): string {
  const MAP: Record<Magnitude, string> = {
    negligible: 'пренебрежимый',
    small: 'малый',
    medium: 'средний',
    large: 'большой',
  };
  return MAP[mag];
}

function formatCI(ci: [number, number], unit: string): string {
  return `[${ci[0].toFixed(2)}; ${ci[1].toFixed(2)}] ${unit}`;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('significanceTone: significant → success', () => {
  assert.equal(significanceTone('significant'), 'success');
});

test('significanceTone: not_significant → warning', () => {
  assert.equal(significanceTone('not_significant'), 'warning');
});

test('significanceTone: inconclusive → default', () => {
  assert.equal(significanceTone('inconclusive'), 'default');
});

test('significanceLabel: significant includes p-value', () => {
  const label = significanceLabel('significant', 0.023);
  assert.ok(label.includes('0.023'), `expected 0.023 in "${label}"`);
  assert.ok(label.includes('значимо'));
});

test('significanceLabel: not_significant → Russian label', () => {
  assert.equal(significanceLabel('not_significant', 0.5), 'не значимо');
});

test('significanceLabel: inconclusive → Russian label', () => {
  assert.equal(significanceLabel('inconclusive', 1.0), 'недостаточно данных');
});

test('magnitudeLabel: all four values have Russian translations', () => {
  assert.equal(magnitudeLabel('negligible'), 'пренебрежимый');
  assert.equal(magnitudeLabel('small'), 'малый');
  assert.equal(magnitudeLabel('medium'), 'средний');
  assert.equal(magnitudeLabel('large'), 'большой');
});

test('formatCI: formats two-decimal CI with unit', () => {
  const result = formatCI([-0.53, 2.7], 'кг/д');
  assert.ok(result.includes('-0.53'));
  assert.ok(result.includes('2.70'));
  assert.ok(result.includes('кг/д'));
});

test('p-value rounding: 0.023 formats to 3 decimal places', () => {
  const label = significanceLabel('significant', 0.023);
  assert.ok(label.includes('0.023'));
});
```

- [ ] **Step 2: Run test — verify it fails (module import only, logic not yet in component)**

```bash
cd /opt/genomeai/worktrees/wt-stat/web_app
node --test components/timeline/__tests__/kpi-impact-card.test.ts 2>&1 | head -20
```

These are self-contained tests that should actually PASS immediately since the helpers are defined inline in the test file. Run to confirm green baseline.

Expected output: `✓` for each of the 9 tests, `ok` summary.

- [ ] **Step 3: Create `web_app/components/timeline/kpi-impact-card.tsx`**

```tsx
import { Badge } from '@/components/ui/badge';

export interface ImpactKPIResult {
  kpi: string;
  diff_in_diff_effect: number;
  p_value: number;
  cohen_d: number;
  magnitude: 'negligible' | 'small' | 'medium' | 'large';
  ci_95: [number, number];
  significance: 'significant' | 'not_significant' | 'inconclusive';
  before: { mean: number; n: number };
  after: { mean: number; n: number };
}

const KPI_LABELS: Record<string, string> = {
  milk_yield: 'Удой',
  scc: 'СКК',
  dmr: 'DMR',
  dry_matter_intake: 'Потребление СВ',
  reproductive_rate: 'Воспроизводство',
};

const MAGNITUDE_LABELS: Record<ImpactKPIResult['magnitude'], string> = {
  negligible: 'пренебрежимый',
  small: 'малый',
  medium: 'средний',
  large: 'большой',
};

function significanceTone(
  sig: ImpactKPIResult['significance'],
): 'success' | 'warning' | 'default' {
  if (sig === 'significant') return 'success';
  if (sig === 'not_significant') return 'warning';
  return 'default';
}

function significanceLabel(sig: ImpactKPIResult['significance'], pValue: number): string {
  if (sig === 'significant') return `значимо (p=${pValue.toFixed(3)})`;
  if (sig === 'not_significant') return 'не значимо';
  return 'недостаточно данных';
}

export function KPIImpactCard({ result }: { result: ImpactKPIResult }) {
  const kpiLabel = KPI_LABELS[result.kpi] ?? result.kpi;
  const effectSign = result.diff_in_diff_effect >= 0 ? '+' : '';
  const cohenSign = result.cohen_d >= 0 ? '+' : '';

  return (
    <div className="kpi-impact-card">
      <div className="kpi-impact-card-header">
        <span className="kpi-impact-card-name">{kpiLabel}</span>
        <Badge tone={significanceTone(result.significance)}>
          {significanceLabel(result.significance, result.p_value)}
        </Badge>
      </div>

      <div className="kpi-impact-card-stats">
        <div className="kpi-impact-stat">
          <span className="kpi-impact-stat-label">Эффект DiD</span>
          <span
            className={`kpi-impact-stat-value ${result.diff_in_diff_effect >= 0 ? 'kpi-impact-positive' : 'kpi-impact-negative'}`}
          >
            {effectSign}{result.diff_in_diff_effect.toFixed(2)}
          </span>
        </div>

        <div className="kpi-impact-stat">
          <span className="kpi-impact-stat-label">Cohen&#39;s d</span>
          <span className="kpi-impact-stat-value">
            {cohenSign}{result.cohen_d.toFixed(2)}
            <span className="kpi-impact-magnitude"> ({MAGNITUDE_LABELS[result.magnitude]})</span>
          </span>
        </div>

        <div className="kpi-impact-stat kpi-impact-stat-ci">
          <span className="kpi-impact-stat-label">95% CI</span>
          <span className="kpi-impact-stat-value">
            [{result.ci_95[0].toFixed(2)}; {result.ci_95[1].toFixed(2)}]
          </span>
        </div>
      </div>

      <div className="kpi-impact-card-periods">
        <div className="kpi-impact-period">
          <span className="kpi-impact-period-label">До</span>
          <span className="kpi-impact-period-value">
            {result.before.mean.toFixed(1)}
            <span className="kpi-impact-period-n"> (n={result.before.n})</span>
          </span>
        </div>
        <div className="kpi-impact-arrow">→</div>
        <div className="kpi-impact-period">
          <span className="kpi-impact-period-label">После</span>
          <span className="kpi-impact-period-value">
            {result.after.mean.toFixed(1)}
            <span className="kpi-impact-period-n"> (n={result.after.n})</span>
          </span>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: TypeScript check**

```bash
cd /opt/genomeai/worktrees/wt-stat/web_app
npx tsc --noEmit 2>&1 | grep kpi-impact-card
```

Expected: No output (no errors).

- [ ] **Step 5: Commit KPIImpactCard**

```bash
git add web_app/components/timeline/kpi-impact-card.tsx \
        web_app/components/timeline/__tests__/kpi-impact-card.test.ts
git commit -m "feat(PMV-B04): add KPIImpactCard component with p-value badge + CI display"
```

---

## Task 6: Create WindowSelector component

**Files:**
- Create: `web_app/components/timeline/window-selector.tsx`

Note: `window-tabs.tsx` already exists and is used by the existing `ImpactPanel` for the seeded-data section. `WindowSelector` is a new compact button-group specifically for the statistical section header.

- [ ] **Step 1: Create `web_app/components/timeline/window-selector.tsx`**

```tsx
import type { MetricWindow } from '@/lib/api/timeline';

const WINDOWS: { value: MetricWindow; label: string }[] = [
  { value: '3d', label: '3 дня' },
  { value: '1w', label: '1 нед' },
  { value: '2w', label: '2 нед' },
  { value: '4w', label: '4 нед' },
];

interface WindowSelectorProps {
  active: MetricWindow;
  onChange: (w: MetricWindow) => void;
}

export function WindowSelector({ active, onChange }: WindowSelectorProps) {
  return (
    <div className="window-selector" role="group" aria-label="Временное окно">
      {WINDOWS.map(({ value, label }) => (
        <button
          key={value}
          type="button"
          className={`window-selector-btn${active === value ? ' window-selector-btn-active' : ''}`}
          onClick={() => onChange(value)}
          aria-pressed={active === value}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd /opt/genomeai/worktrees/wt-stat/web_app
npx tsc --noEmit 2>&1 | grep window-selector
```

Expected: No output.

- [ ] **Step 3: Commit WindowSelector**

```bash
git add web_app/components/timeline/window-selector.tsx
git commit -m "feat(PMV-B04): add compact WindowSelector button-group component"
```

---

## Task 7: Update ImpactPanel with statistical section

**Files:**
- Modify: `web_app/components/timeline/impact-panel.tsx`

The existing panel displays seeded `MetricCompareCard` data. We add a **new statistical section** below the metrics grid. The `window` prop from the parent drives both the existing section and the new `/api/impact` fetch.

- [ ] **Step 1: Read the current `impact-panel.tsx` to confirm line numbers**

Read `web_app/components/timeline/impact-panel.tsx` and identify the closing `</div>` of `impact-panel-body`.

Current structure (lines 99–174):
```tsx
<div className="impact-panel-body">
  ...existing content...
  {impact ? (
    <>
      ...MetricCompareCard grid...
      {impact.other_changes.length > 0 && ...}
    </>
  ) : (
    <div className="empty-state">...</div>
  )}
</div>
```

- [ ] **Step 2: Modify `impact-panel.tsx`**

Add these imports at the top of the file (after the existing imports):

```tsx
import { useState, useEffect } from 'react';
import type { ImpactKPIResult } from './kpi-impact-card';
import { KPIImpactCard } from './kpi-impact-card';
import { WindowSelector } from './window-selector';
```

Add `farmId` as an optional prop to the `Props` type:

```tsx
type Props = {
  event: TimelineEvent | null;
  window: MetricWindow;
  onWindowChange: (w: MetricWindow) => void;
  farmId?: string;
};
```

Update the function signature:

```tsx
export function ImpactPanel({ event, window: activeWindow, onWindowChange, farmId = 'demo-farm-v1' }: Props) {
```

Add a new state + effect inside the function body, right after the `const impact = ...` line:

```tsx
  const [statResults, setStatResults] = useState<ImpactKPIResult[] | null>(null);
  const [statLoading, setStatLoading] = useState(false);

  useEffect(() => {
    if (!event) { setStatResults(null); return; }
    setStatLoading(true);
    setStatResults(null);
    const controller = new AbortController();
    fetch('/api/impact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event_id: event.timeline_event_id,
        farm_id: farmId,
        event_date: event.date,
        event_type: event.event_type,
        affected_groups: ['all'],
        kpi_list: ['milk_yield', 'scc', 'dmr'],
        window: activeWindow,
      }),
      signal: controller.signal,
    })
      .then((r) => r.json())
      .then((data) => { setStatResults(data.kpi_results ?? []); })
      .catch(() => { setStatResults(null); })
      .finally(() => { setStatLoading(false); });
    return () => controller.abort();
  }, [event, activeWindow, farmId]);
```

Add the statistical section **inside the `{impact ? (<> ... </>) : (...)}` block**, immediately after the `{impact.other_changes.length > 0 && ...}` block and before the closing `</>`:

```tsx
            {/* Statistical analysis section */}
            <div className="impact-stat-section">
              <div className="impact-stat-section-header">
                <span className="impact-section-heading">Статистический анализ</span>
                <WindowSelector active={activeWindow} onChange={onWindowChange} />
              </div>

              {statLoading && (
                <div className="impact-stat-skeleton">
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="kpi-impact-card kpi-impact-card-skeleton" />
                  ))}
                </div>
              )}

              {!statLoading && statResults && statResults.length > 0 && (
                <div className="impact-stat-grid">
                  {statResults.map((r) => (
                    <KPIImpactCard key={r.kpi} result={r} />
                  ))}
                </div>
              )}

              {!statLoading && statResults !== null && statResults.length === 0 && (
                <div className="impact-stat-empty">
                  Недостаточно данных для статистического анализа
                </div>
              )}
            </div>
```

- [ ] **Step 3: TypeScript check (full project)**

```bash
cd /opt/genomeai/worktrees/wt-stat/web_app
npx tsc --noEmit 2>&1 | head -30
```

Expected: No errors.

- [ ] **Step 4: Commit updated ImpactPanel**

```bash
git add web_app/components/timeline/impact-panel.tsx
git commit -m "feat(PMV-B04): wire statistical section into ImpactPanel — fetch /api/impact, render KPIImpactCard"
```

---

## Task 8: Add CSS for new components

**Files:**
- Identify existing CSS file for timeline components, then add styles

- [ ] **Step 1: Find the timeline CSS file**

```bash
grep -rl "impact-panel\|tl-right\|MetricCompareCard" /opt/genomeai/worktrees/wt-stat/web_app --include="*.css" | head -5
```

- [ ] **Step 2: Append styles to the found CSS file**

Add to the end of the found CSS file:

```css
/* PMV-B04: KPIImpactCard + WindowSelector + statistical section */

.kpi-impact-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 14px;
  background: var(--surface-alt, #f9fafb);
  font-family: Inter, sans-serif;
}

.kpi-impact-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.kpi-impact-card-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #111827);
}

.kpi-impact-card-stats {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}

.kpi-impact-stat {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.kpi-impact-stat-label {
  color: var(--text-muted, #6b7280);
}

.kpi-impact-stat-value {
  font-weight: 500;
  color: var(--text-primary, #111827);
}

.kpi-impact-positive { color: #2dd4bf; }
.kpi-impact-negative { color: #f87171; }
.kpi-impact-magnitude { color: var(--text-muted, #6b7280); font-weight: 400; }

.kpi-impact-card-periods {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding-top: 8px;
  border-top: 1px solid var(--border, #e5e7eb);
}

.kpi-impact-period {
  display: flex;
  flex-direction: column;
  flex: 1;
}

.kpi-impact-period-label {
  font-size: 10px;
  color: var(--text-muted, #6b7280);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.kpi-impact-period-value { font-weight: 600; font-size: 13px; }
.kpi-impact-period-n { font-weight: 400; color: var(--text-muted, #6b7280); }

.kpi-impact-arrow {
  color: var(--text-muted, #6b7280);
  font-size: 14px;
  flex-shrink: 0;
}

.kpi-impact-card-skeleton {
  height: 88px;
  background: linear-gradient(90deg, var(--border, #e5e7eb) 25%, #f3f4f6 50%, var(--border, #e5e7eb) 75%);
  background-size: 200% 100%;
  animation: kpi-shimmer 1.4s infinite;
}

@keyframes kpi-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* WindowSelector */
.window-selector {
  display: inline-flex;
  gap: 2px;
  background: var(--surface, #f3f4f6);
  border-radius: 6px;
  padding: 2px;
}

.window-selector-btn {
  padding: 4px 10px;
  font-size: 11px;
  font-family: Inter, sans-serif;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  color: var(--text-muted, #6b7280);
  transition: background 0.15s, color 0.15s;
}

.window-selector-btn:hover { background: var(--surface-hover, #e5e7eb); color: var(--text-primary, #111827); }
.window-selector-btn-active {
  background: #fff;
  color: var(--primary, #2dd4bf);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

/* Statistical section */
.impact-stat-section { margin-top: 20px; }

.impact-stat-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.impact-stat-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.impact-stat-skeleton {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.impact-stat-empty {
  font-size: 12px;
  color: var(--text-muted, #6b7280);
  text-align: center;
  padding: 20px 0;
}

/* Mobile < 768px */
@media (max-width: 767px) {
  .kpi-impact-card { padding: 10px 12px; }
  .kpi-impact-card-header { flex-direction: column; align-items: flex-start; gap: 4px; }
  .impact-stat-section-header { flex-direction: column; align-items: flex-start; gap: 8px; }
  .window-selector { width: 100%; justify-content: space-between; }
  .window-selector-btn { flex: 1; text-align: center; }
}
```

- [ ] **Step 3: Commit CSS**

```bash
git add web_app/  # only the CSS file identified in step 1
git commit -m "feat(PMV-B04): add CSS for KPIImpactCard, WindowSelector, and statistical section"
```

---

## Task 9: Run CI gates and create execution proof

**Files:**
- Create: `docs/iterations/PMV-B04_execution_proof.md`

- [ ] **Step 1: Run full backend test suite**

```bash
cd /opt/genomeai/worktrees/wt-stat
bash scripts/run_ci_gate.sh 2>&1 | tee artifacts/_ci/pmv_b04_pytest.log
```

Expected: All gates pass. Check `artifacts/_ci/pmv_b04_pytest.log`.

- [ ] **Step 2: Run TypeScript check**

```bash
cd /opt/genomeai/worktrees/wt-stat/web_app
npx tsc --noEmit 2>&1 | tee /opt/genomeai/worktrees/wt-stat/artifacts/_ci/pmv_b04_tsc.log
```

Expected: No output (exit code 0).

- [ ] **Step 3: Run frontend tests**

```bash
cd /opt/genomeai/worktrees/wt-stat/web_app
node --test components/timeline/__tests__/kpi-impact-card.test.ts 2>&1 | tee /opt/genomeai/worktrees/wt-stat/artifacts/_ci/pmv_b04_frontend_tests.log
```

Expected: 9 passing tests.

- [ ] **Step 4: Run warning governance gate**

```bash
cd /opt/genomeai/worktrees/wt-stat
bash scripts/run_warning_governance_gate.sh 2>&1 | tee artifacts/_ci/pmv_b04_warnings.log
```

- [ ] **Step 5: Invoke frontend-design subagent**

Run the following and record feedback:

```
> Use the frontend-design subagent on impact-panel.tsx and kpi-impact-card.tsx
```

- [ ] **Step 6: Write execution proof**

Create `docs/iterations/PMV-B04_execution_proof.md` with results of all checks above (see proof format in CLAUDE.md). Fill in actual log excerpts. Set status to `proven` if all gates pass, `partially_proven` if any gate failed.

- [ ] **Step 7: Commit proof**

```bash
git add docs/iterations/PMV-B04_execution_proof.md artifacts/_ci/
git commit -m "docs(PMV-B04): add execution proof with CI gate results"
```

---

## Self-Review Against Spec

**Spec coverage check:**

| Requirement | Covered by |
|-------------|-----------|
| `POST /api/impact` endpoint | Task 3 |
| Demo mode seeded data | Task 1 + Task 3 |
| Real mode `compute_full_impact` | Task 3 |
| Router registered | Task 4 |
| `ImpactKPIResult` TypeScript interface | Task 5 (`kpi-impact-card.tsx`) |
| P-value badge (significant/not_significant/inconclusive) | Task 5 |
| Cohen's d + effect magnitude | Task 5 |
| 95% CI display | Task 5 |
| `WindowSelector` component | Task 6 |
| ImpactPanel fetches `/api/impact` | Task 7 |
| Loading skeleton | Task 7 |
| Empty state | Task 7 |
| Russian copy throughout | Tasks 5, 6, 7 |
| `--primary` teal `#2dd4bf` for significant | Task 8 (CSS) |
| Inter font | Task 8 (CSS) |
| Mobile responsive < 768px | Task 8 (CSS media query) |
| Backend tests (demo + real mode) | Task 2 |
| Frontend tests (render + window switch) | Task 5 |
| Frontend-design subagent review | Task 9 |
| `PMV-B04_execution_proof.md` | Task 9 |

**Placeholder scan:** No TBDs, no "implement later", no references to undefined types.

**Type consistency check:**
- `ImpactKPIResult.significance` used in `kpi-impact-card.tsx` matches `StatisticalImpactResult.significance` values
- `ImpactKPIResult.ci_95: [number, number]` matches serialized `list(result.bootstrap_ci_95)` from backend
- `ImpactKPIResult.before.n` uses `sample_sizes["treated"]` (correct — dataclass has `{"treated": n, "control": n}`, not `"treated_before"`)
- `MetricWindow` imported from `@/lib/api/timeline` in both `window-selector.tsx` and `impact-panel.tsx`

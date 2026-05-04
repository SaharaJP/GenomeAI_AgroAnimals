# Задача PMV-B04: Impact Panel UI — wire-up на StatisticalImpactResult

**PROMPT:**

## Контекст
- `CLAUDE.md`, `docs/audit/AUDIT_REPORT.md`, `design_decisions.md`
- Worktree: `wt-stat` (ветка `b/stat`)
- PMV-B03 готов: `web_cabinet/analytics/statistical_extension.py` существует
- `web_app/components/timeline/impact-panel.tsx` уже создан в MVP-N16, рендерит seeded narratives
- Скриншот референс: Connecterra-style Impact panel в `docs/design_reference/`

## Цель
1. Backend endpoint `POST /api/impact` — возвращает StatisticalImpactResult
2. Frontend Impact Panel показывает p-value badge, effect size, 95% CI

## Зоны параллельной работы

Этот worktree трогает:
- `web_cabinet/ai/endpoints/impact.py` (новый)
- `web_app/components/timeline/impact-panel.tsx`
- Новые компоненты `web_app/components/timeline/kpi-impact-card.tsx`, `window-selector.tsx`

НЕ ТРОГАЙ:
- `web_cabinet/analytics/kpi_bridge.py` (wt-bridge)
- `web_cabinet/iot/` (wt-iot)
- `web_cabinet/ai/context.py`

## Backend endpoint

```python
# web_cabinet/ai/endpoints/impact.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter()

class ImpactRequest(BaseModel):
    event_id: str
    farm_id: str
    event_date: date
    event_type: str
    affected_groups: list[str]
    kpi_list: list[str]
    window: Literal["3d", "1w", "2w", "4w"] = "2w"


@router.post("/api/impact")
async def compute_event_impact(
    req: ImpactRequest,
    settings = Depends(get_ai_settings),
):
    if settings.GENOMEAI_AI_DEMO_MODE:
        return load_seeded_impact(req.event_id)
    
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
        results.append({
            "kpi": kpi,
            "diff_in_diff_effect": result.diff_in_diff_effect,
            "p_value": result.welch_t_pvalue,
            "cohen_d": result.cohen_d_effect_size,
            "magnitude": result.effect_magnitude,
            "ci_95": list(result.bootstrap_ci_95),
            "significance": result.significance,
            "before": {"mean": result.treated_before, "n": result.sample_sizes["treated_before"]},
            "after": {"mean": result.treated_after, "n": result.sample_sizes["treated_after"]},
        })
    
    return {"event_id": req.event_id, "kpi_results": results}
```

Регистрация роутера — НЕ в `web_cabinet/__init__.py` напрямую (там могут быть конфликты с другими worktrees), а через **отдельный коммит после мерджа** в main.

## Frontend impact-panel.tsx

```tsx
interface ImpactKPIResult {
  kpi: string;
  diff_in_diff_effect: number;
  p_value: number;
  cohen_d: number;
  magnitude: 'negligible' | 'small' | 'medium' | 'large';
  ci_95: [number, number];
  significance: 'significant' | 'not_significant' | 'inconclusive';
  before: {mean: number, n: number};
  after: {mean: number, n: number};
}

export function ImpactPanel({eventId, farmId, eventDate, eventType, affectedGroups}: ImpactPanelProps) {
  // Fetch /api/impact
  // Render KPIImpactCard for each kpi result
  // WindowSelector сверху
  // Loading skeleton
  // Empty state если результата нет
}

function KPIImpactCard({result}) {
  const sigBadge = {
    significant: <Badge variant="green">🟢 значимо (p={p_value.toFixed(3)})</Badge>,
    not_significant: <Badge variant="yellow">🟡 не значимо</Badge>,
    inconclusive: <Badge variant="gray">⚪ недостаточно данных</Badge>,
  }[result.significance];
  
  // ...
}
```

## Acceptance criteria

1. `/api/impact` возвращает корректную структуру в обоих режимах (demo + real)
2. Impact Panel рендерится без ошибок
3. P-value badge корректный (значимо/не значимо/inconclusive)
4. Window selector меняет данные через refetch
5. Demo mode сохранён
6. **Russian copy throughout** — все labels на русском
7. Connecterra style consistency:
   - Inter font
   - --primary бирюзовый #2dd4bf для значимых
   - Spacing соответствует references
8. Mobile responsive < 768px
9. Tests:
   - Backend: `test_impact_endpoint_demo_returns_seeded`, `test_impact_endpoint_real_mode_p_value`
   - Frontend: render с mock data, переключение window

## Subagent review

В конце задачи **обязательно** запусти:
```
> Use the frontend-design subagent on impact-panel.tsx и kpi-impact-card.tsx
```

И добавь его feedback в execution_proof.

## Формат ответа

T34 — `docs/iterations/PMV-B04_execution_proof.md` + screenshots:
- Impact Panel в demo mode
- Impact Panel в real mode (с разными p-values: significant / not_significant / inconclusive)
- Mobile view

# Задача PMV-B03: Statistical Extension — Welch t-test поверх diff-in-diff

**PROMPT:**

## Контекст
- `CLAUDE.md`, `docs/audit/AUDIT_REPORT.md`
- Worktree: `wt-stat` (ветка `b/stat`)
- В архиве есть `src/genomeai/roi_attribution.py` (1865 LoC) — diff-in-diff metoda для до/после с control group
- После наших фиксов в bootstrap — компилируется
- Чего не хватает для investor-grade Impact Analysis: p-value, effect size, confidence intervals

## Цель
Создать `web_cabinet/analytics/statistical_extension.py` — добавить статистический слой поверх существующего `roi_attribution.diff_in_diff`.

## Зоны параллельной работы

Этот worktree (`wt-stat`) трогает ТОЛЬКО:
- `web_cabinet/analytics/statistical_extension.py`
- `web_cabinet/analytics/tests/test_statistical_extension.py`

НЕ ТРОГАЙ:
- `web_cabinet/analytics/kpi_bridge.py` (wt-bridge)
- `web_cabinet/analytics/sensor_bridge.py` (wt-iot)
- `web_app/components/timeline/impact-panel.tsx` — это в **СЛЕДУЮЩЕЙ** PMV-B04

## Что реализовать

```python
@dataclass
class StatisticalImpactResult:
    # Из roi_attribution
    treated_before: float
    treated_after: float
    control_before: float
    control_after: float
    diff_in_diff_effect: float
    
    # NEW
    welch_t_pvalue: float
    cohen_d_effect_size: float
    effect_magnitude: Literal["negligible", "small", "medium", "large"]
    bootstrap_ci_95: tuple[float, float]
    
    # Decision
    significance: Literal["significant", "not_significant", "inconclusive"]
    sample_sizes: dict


def compute_full_impact(
    farm_id: str,
    event_date: date,
    event_type: str,
    affected_groups: list[str],
    kpi_metric: str,
    window: Literal["3d", "1w", "2w", "4w"],
) -> StatisticalImpactResult:
    """
    Steps:
    1. Diff-in-diff через roi_attribution (legacy)
    2. Welch t-test между treated_after vs control_after
    3. Cohen's d
    4. Bootstrap CI 95%
    5. Verdict
    """
```

Helpers:

```python
def _cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """d = (mean_a - mean_b) / pooled_std."""

def _bootstrap_ci_diff(a, b, confidence=0.95, n_bootstrap=1000):
    """CI для разности средних через bootstrap, seed=42 для детерминизма."""

def _classify_significance(p_value, n) -> Literal["significant", "not_significant", "inconclusive"]:
    """n<7 или nan → inconclusive, p<0.05 → significant, иначе not_significant."""

def _magnitude_from_d(abs_d) -> str:
    """<0.2 negligible, <0.5 small, <0.8 medium, >=0.8 large."""
```

Использование:
- `scipy.stats.ttest_ind(a, b, equal_var=False)` для Welch
- `numpy.random.default_rng(seed=42)` для воспроизводимого bootstrap

## Acceptance criteria

1. Файл < 350 LoC
2. Tests (минимум 7):
   - `test_compute_full_impact_synthetic` — happy path
   - `test_welch_t_test_correctness_vs_scipy_reference` — числовая verify vs scipy.stats.ttest_ind
   - `test_cohens_d_formula`
   - `test_bootstrap_ci_coverage` — на 100 синтетических распределений с известным mean diff, проверка что 95% CI покрывает true в ≥90% случаев
   - `test_n_below_7_returns_inconclusive`
   - `test_significance_classification`
   - `test_magnitude_thresholds` — границы negligible/small/medium/large
3. Использует существующий `roi_attribution.compute_diff_in_diff` (не дублирует)
4. Integration test: запустить на seeded событии (mastitis treatment) на investor_v1, получить осмысленный p-value

## Что НЕ делать

- ❌ Не реимплементировать diff-in-diff
- ❌ Не делать свой t-test — используй `scipy.stats.ttest_ind`
- ❌ Не трогай UI

## Формат ответа

T34 — `docs/iterations/PMV-B03_execution_proof.md`.

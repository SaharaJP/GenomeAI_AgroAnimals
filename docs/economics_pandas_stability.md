# Economics pandas stability

## Scope

T16-04 stabilizes `src/genomeai/economics_v2.py` against pandas FutureWarning without changing formulas, CSV layout, run ids, or итоговые числа.

## What changed

1. Added local dtype-safe helpers for numeric overwrite paths:
   - `_float_series(...)`
   - `_assign_float_where(...)`
2. Replaced the `dm_prices` fallback assignment with a float-aligned overwrite path instead of direct `df.loc[mask, col] = ...` assignment.
3. Added concat normalization helpers:
   - `_normalize_concat_frame(...)`
   - `_concat_legacy_compatible(...)`
4. `econ_daily_out` is now assembled through normalized concat so empty/all-NA placeholder columns do not affect pandas dtype inference.
5. Derived numeric columns like `cost_per_liter_rub` now start from numeric `NaN`, not `pd.NA`, to keep numeric dtype stable during later assignments.

## Compatibility contract

The stabilization is intentionally local to `economics_v2`.

Preserved behavior:
- same formulas;
- same economics run layout under `artifacts/<data_version>/economics_v2/<run_id>/`;
- same file names;
- same CSV columns and ordering after final normalization;
- same output values for key `economics_daily.csv` and `economics_monthly.csv` fixture scenarios.

## Verification

Targeted regression for this step:

```bash
PYTHONPATH=src pytest -q \
  tests/test_t16_04_economics_pandas_stability.py \
  tests/test_t11_01_economics_v2.py \
  tests/test_t11_03_unit_economics.py \
  tests/test_t11_03_roi_attribution.py
```

And then:

```bash
PYTHONPATH=src python -m web_cabinet.smoke --workdir _tmp/t16_04_web_smoke --clean
PYTHONPATH=src python -m genomeai.cli verify_refactor --project-root . --golden golden --report-root artifacts/_verify_refactor_t16_04
```

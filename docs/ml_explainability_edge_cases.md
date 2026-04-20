# ML explainability edge-case stabilization

## Что изменено

В explainability fallback для продуктивности убраны `numpy RuntimeWarning` на малых и вырожденных выборках.

Сделано локально и без изменения внешнего контракта:
- fallback-оценка важности признаков больше не использует прямой `Series.corr(...)` на tiny/degenerate train split;
- добавлен безопасный расчёт абсолютной корреляции, который возвращает `0.0` для пустых, одноточечных и константных серий;
- explainability row helpers устойчиво обрабатывают empty-like input и сохраняют прежние fallback-значения:
  - `insufficient_explainability_data`
  - `no_simple_counterfactual`

## Что не меняется

- формат `explainability_profile.json`;
- поля explainability в `scored_latest.csv` и explanations artifacts;
- контракт `model_card` / scoring outputs / report fact-pack.

## Как проверять

- `pytest -q -W error::RuntimeWarning tests/test_t16_06_ml_explainability_edge_cases.py`
- `python -m web_cabinet.smoke ...`
- `python -m genomeai.cli verify_refactor ...`

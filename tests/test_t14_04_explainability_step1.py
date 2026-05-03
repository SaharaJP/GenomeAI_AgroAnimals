from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from genomeai.copilot_fact_pack import build_copilot_fact_pack_from_assistant_fact_pack
from genomeai.explainability_v1 import explain_row, save_explainability_profile
from genomeai.regular_reports import build_fact_pack_regular


def _demo_pipe() -> Pipeline:
    X = pd.DataFrame(
        {
            'scc_cells_ml': [100000, 150000, 400000, 500000, 250000, 450000],
            'milk_kg': [30, 28, 20, 18, 26, 19],
            'rumination_min': [520, 510, 360, 340, 480, 320],
        }
    )
    y = [0, 0, 1, 1, 0, 1]
    pre = ColumnTransformer([('num', Pipeline([('imputer', SimpleImputer(strategy='median'))]), list(X.columns))])
    pipe = Pipeline([('pre', pre), ('model', GradientBoostingClassifier(random_state=42))])
    pipe.fit(X, y)
    return pipe


def test_explain_row_returns_factors_and_counterfactuals(tmp_path: Path) -> None:
    pipe = _demo_pipe()
    model_dir = tmp_path / 'model'
    model_dir.mkdir(parents=True, exist_ok=True)
    save_explainability_profile(
        model_dir=model_dir,
        features=['scc_cells_ml', 'milk_kg', 'rumination_min'],
        feature_importances=[0.6, 0.25, 0.15],
        baseline_median={'scc_cells_ml': 200000.0, 'milk_kg': 27.0, 'rumination_min': 500.0},
        baseline_scale={'scc_cells_ml': 100000.0, 'milk_kg': 5.0, 'rumination_min': 80.0},
        feature_rules={
            'scc_cells_ml': 'higher_increases_risk',
            'milk_kg': 'lower_increases_risk',
            'rumination_min': 'lower_increases_risk',
        },
        top_k=3,
    )
    profile = json.loads((model_dir / 'explainability_profile.json').read_text(encoding='utf-8'))
    score_df = pd.DataFrame([{'scc_cells_ml': 460000.0, 'milk_kg': 18.5, 'rumination_min': 330.0}])
    row = pd.Series({'risk_proba': 0.91}, name=0)
    res = explain_row(row=row, score_df=score_df, pipe=pipe, profile=profile, cfg={'explainability': {'top_k': 3}})

    assert res['top_factors']
    assert any(item['feature'] == 'scc_cells_ml' for item in res['top_factors'])
    assert 'scc_cells_ml' in res['top_factors_text']
    assert isinstance(res['counterfactuals'], list)
    assert res['counterfactuals_text']


def test_regular_and_copilot_fact_pack_include_explainability_columns(tmp_path: Path) -> None:
    artifacts = tmp_path / 'artifacts'
    mast_dir = artifacts / 'dv_demo' / 'mastitis' / 'scoring' / 'mast_run_001'
    mast_dir.mkdir(parents=True, exist_ok=True)
    (mast_dir / 'scoring_summary.json').write_text(
        json.dumps({'scoring_run': 'mast_run_001', 'asof_date': '2026-03-09', 'horizon_days': 7, 'risk_threshold': 0.7}, ensure_ascii=False),
        encoding='utf-8',
    )
    (mast_dir / 'mastitis_risk_scores.csv').write_text(
        'farm_id,animal_id,risk_proba,risk_flag,explain_top_factors_text,explain_counterfactuals_text\n'
        'farm_1,1001,0.91,1,"scc_cells_ml=460000 (↑ риск)","если milk_kg изменить с 18.5 до 20.0, риск может измениться на -0.12"\n',
        encoding='utf-8',
    )
    (mast_dir / 'mastitis_explanations.csv').write_text(
        'row_id,animal_id,top_factors_text,counterfactuals_text\n1,1001,"scc_cells_ml=460000 (↑ риск)","если milk_kg изменить ..."\n',
        encoding='utf-8',
    )

    fact_pack = build_fact_pack_regular(artifacts_root=artifacts, data_version='dv_demo', asof_date='2026-03-09', period='daily')
    mast = (((fact_pack.get('modules') or {}).get('health') or {}).get('mastitis_risk') or {})
    assert mast.get('available') is True
    assert mast.get('sources', {}).get('explanations_csv', '').endswith('mastitis_explanations.csv')
    assert mast.get('top_risk')[0]['explain_top_factors_text'].startswith('scc_cells_ml')

    copilot = build_copilot_fact_pack_from_assistant_fact_pack(fact_pack)
    tables = copilot.get('tables') or []
    top_risk = next(t for t in tables if t['table_id'] == 'table.modules_health_mastitis_risk.top_risk')
    assert top_risk['rows'][0]['explain_top_factors_text'].startswith('scc_cells_ml')
    assert 'explain_counterfactuals_text' in top_risk['rows'][0]

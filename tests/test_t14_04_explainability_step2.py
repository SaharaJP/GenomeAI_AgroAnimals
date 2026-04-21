from __future__ import annotations

import json
from pathlib import Path

from genomeai.ai_assistant_rag import answer_question_rag
from genomeai.regular_reports import build_fact_pack_regular, generate_regular_report_text_fallback
from genomeai.report import build_fact_pack, generate_report_text_fallback
from streamlit_app.mastitis_ui_utils import mastitis_best_effort_columns


def _write_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _prepare_regular_artifacts(root: Path) -> None:
    mast_dir = root / "dv_demo" / "mastitis" / "scoring" / "mast_run_001"
    mast_dir.mkdir(parents=True, exist_ok=True)
    (mast_dir / "scoring_summary.json").write_text(
        json.dumps({"scoring_run": "mast_run_001", "asof_date": "2026-03-09", "horizon_days": 7, "risk_threshold": 0.7}, ensure_ascii=False),
        encoding="utf-8",
    )
    (mast_dir / "mastitis_risk_scores.csv").write_text(
        "farm_id,animal_id,risk_proba,risk_score,severity,recommended_action,explain_top_factors_text,explain_counterfactuals_text\n"
        "farm_1,1001,0.91,0.91,high,inspect,\"scc_cells_ml=460000 (↑ риск); milk_kg=18.5 (↑ риск)\",\"если milk_kg изменить с 18.5 до 20.0, риск может измениться на -0.12\"\n",
        encoding="utf-8",
    )
    (mast_dir / "mastitis_explanations.csv").write_text(
        "row_id,animal_id,top_factors_text,counterfactuals_text\n1,1001,\"scc_cells_ml=460000 (↑ риск)\",\"если milk_kg изменить ...\"\n",
        encoding="utf-8",
    )


def test_regular_report_text_mentions_explainability(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    _prepare_regular_artifacts(artifacts)
    fp = build_fact_pack_regular(artifacts_root=artifacts, data_version="dv_demo", asof_date="2026-03-09", period="daily")
    mast = (((fp.get("modules") or {}).get("health") or {}).get("mastitis_risk") or {})
    assert (mast.get("explainability") or {}).get("available") is True
    text = generate_regular_report_text_fallback(fp, audience="director")
    assert "Explainability" in text["executive_summary"]
    assert "why=scc_cells_ml=460000" in text["recommendations"]
    assert "counterfactual=" in text["recommendations"]


def test_base_report_text_mentions_explainability(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    base = artifacts / "dv_test"
    _write_json(base / "qc" / "qc_test" / "qc_summary.json", {"qc_status": "PASS", "metrics": {}, "datasets_loaded": []})
    _write_json(base / "models" / "model_test" / "model_card.json", {"metrics": {"mae": 1, "rmse": 2}, "features": {}, "limitations": {}, "target": "milk_305d_kg"})
    _write_json(base / "scoring" / "score_test" / "scoring_summary.json", {"outputs": {"recommendations_xlsx": "NA", "scored_latest_csv": "NA"}, "row_counts": {}})
    _prepare_regular_artifacts(artifacts)
    fp = build_fact_pack(artifacts_root=artifacts, data_version="dv_test", qc_run="qc_test", model_version="model_test", scoring_run="score_test")
    # add mastitis artifacts under dv_test too
    mast_src = artifacts / "dv_demo" / "mastitis"
    mast_dst = artifacts / "dv_test" / "mastitis"
    import shutil
    shutil.copytree(mast_src, mast_dst)
    fp = build_fact_pack(artifacts_root=artifacts, data_version="dv_test", qc_run="qc_test", model_version="model_test", scoring_run="score_test")
    text = generate_report_text_fallback(fp)
    assert "Explainability: частые top-факторы" in text["executive_summary"]
    assert "counterfactual=" in text["recommendations"]


def test_copilot_why_answer_includes_explainability(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    _prepare_regular_artifacts(artifacts)
    res = answer_question_rag(
        artifacts_root=artifacts,
        data_version="dv_demo",
        asof_date="2026-03-09",
        period="daily",
        question="почему риск мастита по farm_1",
        use_llm=False,
        user_permissions=["alerts.view"],
    )
    assert "Top factors:" in res.answer
    assert "Простой контрфакт:" in res.answer


def test_home_v3_mastitis_columns_include_explainability() -> None:
    import pandas as pd

    df = pd.DataFrame([{
        "animal_id": "1001",
        "risk_proba": 0.91,
        "explain_top_factors_text": "scc_cells_ml=460000 (↑ риск)",
        "explain_counterfactuals_text": "если milk_kg изменить...",
    }])
    cols = mastitis_best_effort_columns(df)
    assert "explain_top_factors_text" in cols
    assert "explain_counterfactuals_text" in cols

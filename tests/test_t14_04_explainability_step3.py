from __future__ import annotations

import json
from pathlib import Path

from genomeai.ai_assistant_rag import answer_question_rag
from genomeai.regular_reports import build_fact_pack_regular
from streamlit_app.mastitis_ui_utils import find_mastitis_animal_explainability


def _prepare_artifacts(root: Path) -> None:
    mast_dir = root / "dv_demo" / "mastitis" / "scoring" / "mast_run_002"
    mast_dir.mkdir(parents=True, exist_ok=True)
    (mast_dir / "scoring_summary.json").write_text(
        json.dumps({"scoring_run": "mast_run_002", "asof_date": "2026-03-10", "horizon_days": 7, "risk_threshold": 0.7}, ensure_ascii=False),
        encoding="utf-8",
    )
    (mast_dir / "mastitis_risk_scores.csv").write_text(
        "farm_id,animal_id,risk_proba,risk_score,severity,recommended_action,explain_top_factors_text,explain_counterfactuals_text\n"
        "farm_1,1001,0.91,0.91,high,inspect,\"scc_cells_ml=460000 (↑ риск)\",\"если milk_kg изменить с 18.5 до 20.0, риск может измениться на -0.12\"\n"
        "farm_1,2002,0.83,0.83,high,recheck,\"days_in_milk=12 (↑ риск); parity=1 (↑ риск)\",\"если days_in_milk изменить с 12 до 20, риск может измениться на -0.08\"\n",
        encoding="utf-8",
    )


def test_regular_fact_pack_includes_animal_explainability_table(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    _prepare_artifacts(artifacts)
    fp = build_fact_pack_regular(artifacts_root=artifacts, data_version="dv_demo", asof_date="2026-03-10", period="daily")
    mast = (((fp.get("modules") or {}).get("health") or {}).get("mastitis_risk") or {})
    rows = mast.get("animal_explainability") or []
    assert len(rows) == 2
    assert rows[1]["animal_id"] == 2002 or rows[1]["animal_id"] == "2002"
    assert "days_in_milk=12" in rows[1]["explain_top_factors_text"]


def test_copilot_why_by_animal_id_prefers_matching_explainability_row(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    _prepare_artifacts(artifacts)
    res = answer_question_rag(
        artifacts_root=artifacts,
        data_version="dv_demo",
        asof_date="2026-03-10",
        period="daily",
        question="почему риск мастита по animal_id=2002",
        use_llm=False,
        user_permissions=["alerts.view"],
    )
    assert "days_in_milk=12" in res.answer
    assert "-0.08" in res.answer


def test_find_mastitis_animal_explainability_returns_card_for_animal() -> None:
    import pandas as pd

    df = pd.DataFrame([
        {"animal_id": "1001", "risk_proba": 0.91, "severity": "high", "explain_top_factors_text": "A", "explain_counterfactuals_text": "B"},
        {"animal_id": "2002", "risk_proba": 0.83, "severity": "high", "explain_top_factors_text": "C", "explain_counterfactuals_text": "D"},
    ])
    card = find_mastitis_animal_explainability(df, animal_id="2002")
    assert card["available"] is True
    assert card["animal_id"] == "2002"
    assert card["top_factors_text"] == "C"
    assert card["counterfactuals_text"] == "D"

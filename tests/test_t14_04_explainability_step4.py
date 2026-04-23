from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from docx import Document

from genomeai.ai_assistant_rag import _extract_explainability_from_rows
from genomeai.qc import run_qc
from genomeai.report import build_fact_pack, run_report
from genomeai.score import run_scoring
from genomeai.train import train_productivity_model
from streamlit_app.mastitis_ui_utils import find_productivity_animal_explainability


def _prep_canonical(tmp_path: Path, data_version: str) -> None:
    canonical_dir = tmp_path / data_version / "canonical"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    base = Path(__file__).resolve().parents[1] / "data" / "examples"
    for fn in ["dm_farms.csv", "dm_animals.csv", "dm_lactations.csv"]:
        (canonical_dir / fn).write_bytes((base / fn).read_bytes())


def test_productivity_explainability_artifacts_are_created(tmp_path: Path) -> None:
    dv = "dv_t14_04_step4"
    _prep_canonical(tmp_path, dv)
    qc = run_qc(data_version=dv, artifacts_root=tmp_path)
    tr = train_productivity_model(artifacts_root=tmp_path, data_version=dv, qc_run=qc["qc_run"])
    assert tr["ok"] is True
    model_dir = Path(tr["model_dir"])
    assert (model_dir / "explainability_profile.json").exists()
    profile = json.loads((model_dir / "explainability_profile.json").read_text(encoding="utf-8"))
    assert profile.get("task_kind") == "regression"

    sc = run_scoring(artifacts_root=tmp_path, data_version=dv, model_version=tr["model_version"])
    assert sc["ok"] is True
    scored = pd.read_csv(Path(sc["outputs"]["scored_latest_csv"]))
    assert "explain_top_factors_text" in scored.columns
    assert "explain_counterfactuals_text" in scored.columns
    assert (scored["explain_top_factors_text"] != "insufficient_explainability_data").any()
    assert Path(sc["outputs"]["explanations_csv"]).exists()


def test_productivity_explainability_visible_in_report_factpack_and_docx(tmp_path: Path) -> None:
    dv = "dv_t14_04_step4_report"
    _prep_canonical(tmp_path, dv)
    qc = run_qc(data_version=dv, artifacts_root=tmp_path)
    tr = train_productivity_model(artifacts_root=tmp_path, data_version=dv, qc_run=qc["qc_run"])
    sc = run_scoring(artifacts_root=tmp_path, data_version=dv, model_version=tr["model_version"])

    fact_pack = build_fact_pack(artifacts_root=tmp_path, data_version=dv, qc_run=qc["qc_run"], model_version=tr["model_version"], scoring_run=sc["scoring_run"])
    prod = fact_pack.get("productivity_explainability") or {}
    assert prod.get("available") is True
    assert (prod.get("animal_explainability") or [])

    rr = run_report(artifacts_root=tmp_path, data_version=dv, qc_run=qc["qc_run"], model_version=tr["model_version"], scoring_run=sc["scoring_run"], mode="fallback", make_pdf=False)
    assert rr["ok"] is True
    doc = Document(rr["outputs"]["report_docx"])
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Explainability (productivity ML)" in full_text
    assert "Частые top-факторы по продуктивности" in full_text or "Контрфакт animal_id=" in full_text


def test_productivity_explainability_used_by_copilot_picker_and_ui_utils() -> None:
    rows = [
        {"animal_id": "1001", "explain_top_factors_text": "parity=2 (↑ прогноз, baseline=1.0)", "explain_counterfactuals_text": "если parity изменить с 2 до 3, прогноз продуктивности может измениться на 120.00 кг"},
        {"animal_id": "2002", "y_pred": 9100.0, "action": "PRIORITY", "confidence": "HIGH", "explain_top_factors_text": "age_at_calving=2.4 (↑ прогноз, baseline=2.0)", "explain_counterfactuals_text": "если age_at_calving изменить с 2.4 до 2.7, прогноз продуктивности может измениться на 95.00 кг"},
    ]
    why, cf = _extract_explainability_from_rows(rows, "почему по animal_id=2002")
    assert why and "age_at_calving" in why
    assert cf and "95.00 кг" in cf

    df = pd.DataFrame(rows)
    card = find_productivity_animal_explainability(df, animal_id="2002")
    assert card.get("available") is True
    assert "age_at_calving" in str(card.get("top_factors_text"))

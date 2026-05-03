from __future__ import annotations

from pathlib import Path

from genomeai.ai_assistant_rag import build_chunks_from_fact_pack, retrieve_chunks
from genomeai.ai_assistant_rag import _fallback_answer  # type: ignore
from genomeai.report import generate_report_text_fallback
from genomeai.regular_reports import generate_regular_report_text_fallback


def test_report_fallback_includes_playbook_block() -> None:
    fp = {
        "versions": {"data_version": "dv", "qc_run": "qc", "model_version": "m", "scoring_run": "s"},
        "qc": {"qc_status": "FAIL"},
        "ml": {"metrics": {"mae": 1.0, "rmse": 2.0}, "limitations": {}},
        "scoring": {"row_counts": {"n_animals_ranked": 1, "n_priority": 1, "n_observe": 0, "n_cull_candidates": 0}},
        "playbooks": {
            "recommended": [
                {
                    "target_kind": "alert",
                    "target_type": "QC.GENERIC",
                    "farm_id": "",
                    "version_id": "v1",
                    "name": "PB QC",
                    "source": "defaults_yaml",
                    "steps": [{"title": "Шаг 1", "details": "Сделать X"}],
                }
            ]
        },
    }
    nar = generate_report_text_fallback(fp)
    assert "PB QC" in nar.get("recommendations", "")
    assert "Шаг 1" in nar.get("recommendations", "")


def test_regular_report_fallback_includes_playbook_for_alert() -> None:
    fp = {
        "period": "daily",
        "asof_date": "2025-01-31",
        "versions": {"data_version": "dv", "model_version": "NA"},
        "modules": {
            "kpi": {"available": False},
            "alerts_v2": {
                "count": 1,
                "top": [
                    {
                        "alert_type": "ML.MASTITIS_RISK",
                        "severity": "HIGH",
                        "title": "Test",
                        "object_type": "animal",
                        "object_id": "a1",
                        "why": {"summary": "x"},
                    }
                ],
            },
            "playbooks": {
                "recommended": [
                    {
                        "target_kind": "alert",
                        "target_type": "ML.MASTITIS_RISK",
                        "version_id": "v2",
                        "name": "PB Mastitis",
                        "steps": [{"title": "Проверить данные"}, {"title": "Осмотр"}],
                    }
                ]
            },
            "health": {"mastitis_risk": {"available": False}},
            "repro": {"available": False},
            "mating": {"available": False},
            "economics": {"available": False},
        },
        "disclaimer": "",
    }
    nar = generate_regular_report_text_fallback(fp, audience="director")
    txt = nar.get("recommendations", "")
    assert "PB Mastitis" in txt
    assert "Проверить данные" in txt


def test_copilot_fallback_surfaces_playbook_chunk() -> None:
    fp = {
        "period": "daily",
        "asof_date": "2025-01-31",
        "versions": {"data_version": "dv", "model_version": "NA"},
        "modules": {},
        "assistant_knowledge": {
            "playbooks": {
                "active": [
                    {
                        "target_kind": "alert",
                        "target_type": "ML.MASTITIS_RISK",
                        "farm_id": "",
                        "version_id": "v3",
                        "name": "PB Mastitis",
                        "description": "",
                        "steps": [{"title": "Проверить данные"}, {"title": "Осмотр"}],
                        "sources": {"defaults_yaml": "configs/playbooks/defaults.yaml"},
                    }
                ],
                "sources": {"defaults_yaml": "configs/playbooks/defaults.yaml"},
            }
        },
        "disclaimer": "Decision-support",
    }

    chunks = build_chunks_from_fact_pack(fp)
    got = retrieve_chunks("что делать по ML.MASTITIS_RISK", chunks, top_k=6)
    ans, _, _ = _fallback_answer("что делать", got, "Decision-support")
    assert "Рекомендуемый план действий" in ans
    assert "[playbook]" in ans

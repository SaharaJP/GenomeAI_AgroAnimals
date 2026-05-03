from __future__ import annotations

from pathlib import Path

import genomeai.ai_assistant_rag as ragmod
from genomeai.ai_assistant_rag import _source_only_answer, build_chunks_from_fact_pack, retrieve_chunks
from genomeai.copilot_fact_pack import build_copilot_fact_pack_from_assistant_fact_pack


def _demo_assistant_fact_pack() -> dict:
    fp = {
        "period": "daily",
        "asof_date": "2026-03-09",
        "versions": {"data_version": "dv_demo", "model_version": "mdl_001"},
        "modules": {
            "kpi": {
                "available": True,
                "run_id": "kpi_run_001",
                "kpi_count": 3,
                "alert_count": 1,
                "kpi_wide_top": [{"farm_id": "farm_1", "milk_kg": 123.4}],
                "sources": {
                    "kpi_summary": "/tmp/kpi_summary.json",
                    "kpi_wide": "/tmp/kpi_wide.csv",
                },
            }
        },
        "assistant_knowledge": {},
    }
    fp["copilot_fact_pack"] = build_copilot_fact_pack_from_assistant_fact_pack(fp)
    return fp


def test_source_only_answer_emits_inline_citations() -> None:
    fp = _demo_assistant_fact_pack()
    chunks = build_chunks_from_fact_pack(fp)
    retrieved = retrieve_chunks("покажи kpi_count и kpi_wide_top", chunks, top_k=8)

    answer, citations, _ = _source_only_answer(
        "покажи kpi_count и kpi_wide_top",
        retrieved,
        "Decision-support only.",
        cfg={"answer": {"max_facts": 5, "max_tables": 3, "max_missing_sections": 3}},
    )

    assert "Ответ сформирован только по подтверждённым данным copilot_fact_pack." in answer
    assert "modules.kpi.kpi_count = 3" in answer
    assert "modules.kpi.kpi_wide_top | row_count=1" in answer
    assert "[Источник:" in answer
    assert "fact.modules_kpi.kpi_count" in answer
    assert "metric=kpi_count" in answer
    assert "run_id=kpi_run_001" in answer
    assert citations


def test_answer_question_rag_uses_strict_source_only_template(monkeypatch, tmp_path: Path) -> None:
    fp = _demo_assistant_fact_pack()

    monkeypatch.setattr(ragmod, "build_fact_pack_for_assistant", lambda **kwargs: fp)

    res = ragmod.answer_question_rag(
        artifacts_root=tmp_path / "artifacts",
        data_version="dv_demo",
        asof_date="2026-03-09",
        period="daily",
        question="покажи kpi_count",
        use_llm=True,
    )

    assert res.used_llm is False
    assert "Ответ сформирован только по подтверждённым данным copilot_fact_pack." in res.answer
    assert "modules.kpi.kpi_count = 3" in res.answer
    assert "[Источник:" in res.answer
    assert "Источники/версии:" in res.answer


def test_missing_data_response_stays_request_for_upload(tmp_path: Path) -> None:
    res = ragmod.answer_question_rag(
        artifacts_root=tmp_path / "artifacts",
        data_version="dv_empty",
        asof_date="2026-03-09",
        period="daily",
        question="покажи прибыль по ферме",
        use_llm=True,
    )

    assert "Недостаточно фактов" in res.answer
    assert "Нужны данные" in res.answer
    assert "Как получить" in res.answer
    assert "run_id" in res.answer

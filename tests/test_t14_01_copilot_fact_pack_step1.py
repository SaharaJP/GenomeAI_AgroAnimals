from __future__ import annotations

from pathlib import Path

from genomeai.ai_assistant_rag import answer_question_rag, build_chunks_from_fact_pack, build_fact_pack_for_assistant
from genomeai.copilot_fact_pack import build_copilot_fact_pack_from_assistant_fact_pack


def test_copilot_fact_pack_normalizes_metrics_tables_and_sources() -> None:
    assistant_fp = {
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

    fact_pack = build_copilot_fact_pack_from_assistant_fact_pack(assistant_fp)
    assert fact_pack["schema"] == "genomeai.copilot.fact_pack.v1"
    assert any(f["metric_name"] == "kpi_count" and f["run_id"] == "kpi_run_001" for f in fact_pack["facts"])
    assert any(t["table"] == "kpi_wide_top" and t["row_count"] == 1 for t in fact_pack["tables"])
    assert fact_pack["sources"]
    assert all(src.get("section") for src in fact_pack["sources"].values())


def test_assistant_builds_chunks_from_copilot_fact_pack() -> None:
    assistant_fp = {
        "period": "daily",
        "asof_date": "2026-03-09",
        "versions": {"data_version": "dv_demo", "model_version": "mdl_001"},
        "modules": {
            "kpi": {
                "available": True,
                "run_id": "kpi_run_001",
                "kpi_count": 3,
                "sources": {"kpi_summary": "/tmp/kpi_summary.json"},
            }
        },
        "assistant_knowledge": {},
    }
    assistant_fp["copilot_fact_pack"] = build_copilot_fact_pack_from_assistant_fact_pack(assistant_fp)

    chunks = build_chunks_from_fact_pack(assistant_fp)
    assert chunks
    text = "\n".join(ch.text for ch in chunks)
    assert "[fact]" in text
    assert "fact.modules_kpi.kpi_count" in text
    citations = [c for ch in chunks for c in ch.citations]
    assert any(c.section == "modules.kpi" and c.metric == "kpi_count" for c in citations)


def test_answer_requests_missing_data_when_fact_pack_is_empty(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    res = answer_question_rag(
        artifacts_root=artifacts_root,
        data_version="dv_empty",
        asof_date="2026-03-09",
        period="daily",
        question="покажи KPI молока",
        use_llm=False,
    )
    assert "Недостаточно фактов" in res.answer
    assert "Нужны данные" in res.answer
    assert "run_id" in res.answer


def test_builder_attaches_copilot_fact_pack_section(tmp_path: Path) -> None:
    fp = build_fact_pack_for_assistant(
        artifacts_root=tmp_path / "artifacts",
        data_version="dv_demo",
        asof_date="2026-03-09",
        period="daily",
        max_rows=10,
    )
    copilot = fp.get("copilot_fact_pack") or {}
    assert copilot.get("schema") == "genomeai.copilot.fact_pack.v1"
    assert "missing_data_requests" in copilot

from __future__ import annotations

import sqlite3
import sys
import types
from pathlib import Path

import genomeai.ai_assistant_rag as ragmod
from genomeai.ai_assistant_rag import _post_validate_llm_answer, build_chunks_from_fact_pack, retrieve_chunks
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


def test_copilot_fact_pack_has_deep_links() -> None:
    fp = _demo_assistant_fact_pack()["copilot_fact_pack"]

    assert fp["facts"]
    assert fp["tables"]
    assert fp["sources"]
    assert str(fp["facts"][0].get("deep_link", "")).startswith("genomeai://copilot/fact?")
    assert str(fp["tables"][0].get("deep_link", "")).startswith("genomeai://copilot/fact?")
    first_source = next(iter(fp["sources"].values()))
    assert str(first_source.get("deep_link", "")).startswith("genomeai://copilot/fact?")


def test_post_validate_accepts_supported_target_links() -> None:
    fp = _demo_assistant_fact_pack()
    chunks = build_chunks_from_fact_pack(fp)
    retrieved = retrieve_chunks("покажи kpi_count", chunks, top_k=6)

    answer = (
        "Подтверждено: modules.kpi.kpi_count = 3 "
        "[Источник: fact_id=fact.modules_kpi.kpi_count; section=modules.kpi; table=kpi_summary; "
        "metric=kpi_count; run_id=kpi_run_001; report_version=NA; "
        "target=genomeai://copilot/fact?data_version=dv_demo&section=modules.kpi&table=kpi_summary&metric=kpi_count&run_id=kpi_run_001&report_version=NA&fact_id=fact.modules_kpi.kpi_count]"
    )
    ok, reason = _post_validate_llm_answer(answer, retrieved=retrieved, require_target_links=True)
    assert ok is True
    assert reason == "ok"


def test_llm_invalid_answer_falls_back_and_writes_audit(monkeypatch, tmp_path: Path) -> None:
    fp = _demo_assistant_fact_pack()
    db_path = tmp_path / "web.db"

    monkeypatch.setattr(ragmod, "build_fact_pack_for_assistant", lambda **kwargs: fp)
    monkeypatch.setattr(
        ragmod,
        "load_copilot_answer_config",
        lambda cfg_path=None: {
            "answer": {
                "strict_source_only": False,
                "require_inline_citations": True,
                "max_facts": 5,
                "max_tables": 3,
                "max_missing_sections": 3,
                "max_sources": 25,
            },
            "llm": {
                "enabled": True,
                "mode": "allow",
                "post_validate_enabled": True,
                "require_target_links": True,
            },
        },
    )

    class _FakeResponse:
        def __init__(self, content: str) -> None:
            self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=content))]

    class _FakeCompletions:
        @staticmethod
        def create(**kwargs):
            return _FakeResponse("Свободный ответ без источников: KPI = 999")

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key
            self.chat = _FakeChat()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    sys.modules["openai"] = types.SimpleNamespace(OpenAI=_FakeOpenAI)

    res = ragmod.answer_question_rag(
        artifacts_root=tmp_path / "artifacts",
        data_version="dv_demo",
        asof_date="2026-03-09",
        period="daily",
        question="покажи kpi_count",
        web_db_path=db_path,
        use_llm=True,
    )

    assert res.used_llm is False
    assert "Ответ сформирован только по подтверждённым данным copilot_fact_pack." in res.answer
    assert "target=genomeai://copilot/fact?" in res.answer

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    rows = conn.execute(
        "SELECT action, status, error FROM audit_log WHERE object_type='copilot' ORDER BY id ASC"
    ).fetchall()
    conn.close()

    actions = [row[0] for row in rows]
    assert "assistant.copilot.llm_post_validate" in actions
    assert "assistant.copilot.answer" in actions
    fallback_rows = [row for row in rows if row[0] == "assistant.copilot.llm_post_validate"]
    assert fallback_rows
    assert fallback_rows[-1][1] == "FALLBACK"
    assert fallback_rows[-1][2] == "missing_inline_citations"

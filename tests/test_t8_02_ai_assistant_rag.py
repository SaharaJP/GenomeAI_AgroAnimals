from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from genomeai.ai_assistant_rag import (
    answer_question_rag,
    build_chunks_from_fact_pack,
    build_fact_pack_for_assistant,
    evaluate_guardrails,
    retrieve_chunks,
)
from genomeai.assistant_log import append_assistant_log, list_assistant_logs


TEST_CASES = [
    {"q": "поставь диагноз мастит", "allowed": False, "reason": "diagnosis_or_treatment_request"},
    {"q": "назначь лечение антибиотиком", "allowed": False, "reason": "diagnosis_or_treatment_request"},
    {"q": "какая сегодня погода", "allowed": False, "reason": "out_of_scope_non_system"},
    {"q": "покажи KPI молока", "allowed": True},
    {"q": "какие алерты по маститу", "allowed": True},
    {"q": "что с воспроизводством", "allowed": True},
    {"q": "покажи worklist на осеменение", "allowed": True},
    {"q": "почему бык X запрещён", "allowed": True},
    {"q": "какие решения принимали пользователи", "allowed": True},
    {"q": "сводка экономики и маржи", "allowed": True},
    {"q": "дай ссылку на исходники отчёта", "allowed": True},
    {"q": "выведи таблицу decision log", "allowed": True},
    {"q": "покажи отчёт директора", "allowed": True},
    {"q": "какие данные использованы", "allowed": True},
    {"q": "что делать по алертам", "allowed": True},
]


def test_guardrails_cases() -> None:
    for tc in TEST_CASES:
        gd = evaluate_guardrails(tc["q"])
        assert gd.allowed is tc["allowed"]
        if not gd.allowed:
            assert gd.reason == tc["reason"]


def test_fact_pack_and_retrieval_smoke(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    dv = "dv_test"
    web_db = tmp_path / "web.db"

    fp = build_fact_pack_for_assistant(
        artifacts_root=artifacts_root,
        data_version=dv,
        asof_date="2025-01-31",
        period="daily",
        web_db_path=web_db,
        max_rows=20,
    )
    chunks = build_chunks_from_fact_pack(fp)
    assert isinstance(chunks, list)

    got = retrieve_chunks("kpi молока", chunks, top_k=5)
    assert len(got) <= 5


def test_answer_contains_versions_and_sources(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    dv = "dv_test"

    res = answer_question_rag(
        artifacts_root=artifacts_root,
        data_version=dv,
        asof_date="2025-01-31",
        period="daily",
        question="покажи KPI молока",
        web_db_path=None,
        use_llm=False,
    )
    assert res.guardrails.get("allowed") is True
    assert "Источники/версии" in res.answer
    assert res.versions.get("data_version")


def test_refusal_has_trace_versions(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    dv = "dv_test"
    res = answer_question_rag(
        artifacts_root=artifacts_root,
        data_version=dv,
        asof_date="2025-01-31",
        period="daily",
        question="поставь диагноз",
        use_llm=False,
    )
    assert res.guardrails.get("allowed") is False
    assert "Trace versions" in res.answer


def test_assistant_log_roundtrip(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    dv = "dv_test"
    db_path = tmp_path / "web.db"

    res = answer_question_rag(
        artifacts_root=artifacts_root,
        data_version=dv,
        asof_date="2025-01-31",
        period="daily",
        question="покажи KPI молока",
        web_db_path=db_path,
        use_llm=False,
    )
    row_id = append_assistant_log(
        db_path=db_path,
        ts="2025-01-31T00:00:00Z",
        tenant_id="default",
        user_id=1,
        username="tester",
        response=res,
    )
    assert row_id > 0

    logs = list_assistant_logs(db_path=db_path, tenant_id="default", limit=50)
    assert len(logs) >= 1
    assert logs[0].get("response")


def test_decision_log_v2_append_smoke(tmp_path: Path) -> None:
    # Ensure we can append a decision referencing assistant response.
    from web_cabinet.db import init_db
    from web_cabinet.decision_log_v2 import DecisionCreate, append_decision

    db_path = tmp_path / "web.db"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)

    d = DecisionCreate(
        recommendation_id="q1",
        action="assistant.recommendation",
        user_id=1,
        username="tester",
        reason="test",
        comment=None,
        related_alert=None,
        object_type="farm",
        object_id="farm_1",
        farm_id="farm_1",
        group_id=None,
        data_version="dv_test",
        model_version="NA",
        report_version="NA",
        qc_run=None,
        scoring_run=None,
        metadata={"assistant": {"query_id": "q1"}},
    )
    decision_id = append_decision(conn, tenant_id="default", d=d)
    assert isinstance(decision_id, str) and len(decision_id) > 0

    row = conn.execute("SELECT COUNT(*) AS n FROM decision_log_v2").fetchone()[0]
    assert int(row) == 1
    conn.close()

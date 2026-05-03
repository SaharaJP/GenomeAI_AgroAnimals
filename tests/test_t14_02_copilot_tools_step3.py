from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from genomeai.ai_assistant_rag import answer_question_rag
from web_cabinet.db import init_db
from web_cabinet.playbooks_v1 import PlaybookCreate, create_playbook_version
from web_cabinet.tasks_v1 import TaskCreate, create_task


def _write_demo_artifacts(root: Path) -> None:
    kpi_dir = root / "dv_demo" / "runs" / "kpi_run_001" / "kpi"
    kpi_dir.mkdir(parents=True, exist_ok=True)
    (kpi_dir / "kpi_summary.json").write_text(
        json.dumps({"run_id": "kpi_run_001", "kpi_count": 3, "alert_count": 2}, ensure_ascii=False),
        encoding="utf-8",
    )
    (kpi_dir / "kpi_wide.csv").write_text(
        "farm_id,milk_kg\nfarm_1,123.4\nfarm_2,111.1\n",
        encoding="utf-8",
    )
    (kpi_dir / "kpi_alerts.csv").write_text(
        "alert_id,severity,farm_id\nalert_1,high,farm_1\nalert_2,medium,farm_2\n",
        encoding="utf-8",
    )

    econ_dir = root / "dv_demo" / "economics" / "econ_run_001"
    econ_dir.mkdir(parents=True, exist_ok=True)
    (econ_dir / "summary_farm.csv").write_text(
        "farm_id,revenue_milk,margin_total\nfarm_1,100000,42000\nfarm_2,90000,35000\n",
        encoding="utf-8",
    )
    (econ_dir / "whatif_params.json").write_text(
        json.dumps({"economics_run": "econ_run_001", "scenario_name": "base"}, ensure_ascii=False),
        encoding="utf-8",
    )

    mast_dir = root / "dv_demo" / "mastitis" / "scoring" / "mast_run_001"
    mast_dir.mkdir(parents=True, exist_ok=True)
    (mast_dir / "scoring_summary.json").write_text(
        json.dumps(
            {
                "scoring_run": "mast_run_001",
                "asof_date": "2026-03-09",
                "horizon_days": 7,
                "risk_threshold": 0.7,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (mast_dir / "mastitis_risk_scores.csv").write_text(
        "farm_id,animal_id,risk_score,severity\nfarm_1,1001,0.91,high\nfarm_2,2002,0.45,medium\n",
        encoding="utf-8",
    )


def _build_web_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    task_id = create_task(
        conn,
        tenant_id="default",
        t=TaskCreate(
            task_type="health.check",
            title="Проверить животное 1001",
            priority=1,
            related_alert="alert_1",
            object_type="animal",
            object_id="1001",
            data_version="dv_demo",
        ),
    )
    conn.execute("UPDATE tasks_v1 SET status='open', assignee_team='vet' WHERE task_id=?", (task_id,))
    create_playbook_version(
        conn,
        tenant_id="default",
        pb=PlaybookCreate(
            target_kind="alert",
            target_type="mastitis",
            name="Проверка мастита",
            description="Проверить животное и качество молока",
            steps=[
                {"title": "Осмотр животного", "details": "Сверить клинические признаки"},
                {"title": "Проверка данных", "details": "Сравнить SCC и milk_kg"},
            ],
            set_active=True,
        ),
    )
    conn.commit()
    conn.close()


def test_answer_question_rag_uses_cost_template(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_demo_artifacts(artifacts)

    res = answer_question_rag(
        artifacts_root=artifacts,
        data_version="dv_demo",
        asof_date="2026-03-09",
        period="daily",
        question="сколько стоит по farm_1",
        use_llm=False,
        user_permissions=["economics.view"],
    )
    assert "Tool route: query_economics" in res.answer
    assert "Подтверждённая экономика:" in res.answer
    assert "Строка экономики:" in res.answer
    assert "farm_id=farm_1" in res.answer
    assert "revenue_milk=100000" in res.answer
    assert "[Источник:" in res.answer


def test_answer_question_rag_uses_tasks_template_with_playbook(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_demo_artifacts(artifacts)
    db_path = tmp_path / "web.db"
    _build_web_db(db_path)

    res = answer_question_rag(
        artifacts_root=artifacts,
        data_version="dv_demo",
        asof_date="2026-03-09",
        period="daily",
        question="что делать по животному 1001",
        web_db_path=db_path,
        use_llm=False,
        user_permissions=["tasks.view", "playbooks.view", "alerts.view"],
    )
    assert "Tool route: query_tasks" in res.answer
    assert "Что делать сейчас:" in res.answer
    assert "Проверить животное 1001" in res.answer
    assert "status=open" in res.answer
    assert "Дополнительный playbook:" in res.answer
    assert "Проверка мастита" in res.answer
    assert "[Источник:" in res.answer


def test_answer_question_rag_uses_anomaly_why_template(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    _write_demo_artifacts(artifacts)
    db_path = tmp_path / "web.db"
    _build_web_db(db_path)

    res = answer_question_rag(
        artifacts_root=artifacts,
        data_version="dv_demo",
        asof_date="2026-03-09",
        period="daily",
        question="почему риск мастита по farm_1",
        web_db_path=db_path,
        use_llm=False,
        user_permissions=["alerts.view", "playbooks.view"],
    )
    assert "Tool route: query_anomalies" in res.answer
    assert "Почему Copilot считает это отклонением:" in res.answer
    assert "Подтверждающая выборка:" in res.answer
    assert "Что проверить/сделать:" in res.answer
    assert "Проверка мастита" in res.answer
    assert "[Источник:" in res.answer

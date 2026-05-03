from __future__ import annotations

import shutil
from pathlib import Path

from genomeai.economics_v2 import run_economics_v2
from genomeai.template_reports import run_template_report


def test_template_report_includes_economics_section(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    fixtures = repo_root / "data" / "fixtures" / "target_v2"
    assert fixtures.exists()

    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    dv = "dv_test"

    # build a minimal canonical dir for other report blocks (best-effort)
    canon = artifacts / dv / "canonical"
    canon.mkdir(parents=True, exist_ok=True)
    for p in fixtures.glob("*.csv"):
        shutil.copy2(p, canon / p.name)

    res = run_economics_v2(
        artifacts_root=artifacts,
        data_version=dv,
        date_from="2025-01-05",
        date_to="2025-01-05",
        cfg_path=repo_root / "configs" / "economics" / "economics_v2.yaml",
        input_dir=fixtures,
        tenant_id="default",
    )
    assert res.get("ok") is True

    tpl = {
        "template_id": "t_test",
        "name": "Test economics",
        "scope": "user",
        "sections": ["economics"],
        "metrics": [],
        "options": {"role": "director"},
    }

    out = run_template_report(
        artifacts_root=artifacts,
        data_version=dv,
        asof_date="2025-01-05",
        template=tpl,
        inputs={"alerts": [], "tasks": [], "decisions": []},
        mode="fallback",
        report_version="rep_test",
    )
    assert out.get("ok") is True

    md_path = Path(out["outputs"]["director_md"])
    txt = md_path.read_text(encoding="utf-8")
    assert "## Economics" in txt
    assert "economics_run" in txt
    assert "₽" in txt

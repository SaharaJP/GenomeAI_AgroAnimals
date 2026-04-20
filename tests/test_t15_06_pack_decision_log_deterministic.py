from __future__ import annotations

import hashlib
from pathlib import Path

from genomeai.decision_log import init_decision_log


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_t15_06_decision_log_template_exports_are_deterministic_with_fixed_created_at(tmp_path: Path) -> None:
    for root in (tmp_path / "a", tmp_path / "b"):
        scored = root / "dv_1" / "scoring" / "scr_1"
        scored.mkdir(parents=True, exist_ok=True)
        (scored / "scored_latest.csv").write_text(
            "animal_id,lactation_no,action,farm_id\nA001,1,PRIORITY,F001\n",
            encoding="utf-8",
        )

    first = init_decision_log(
        artifacts_root=tmp_path / "a",
        data_version="dv_1",
        scoring_run="scr_1",
        user="pilot_pack",
        template_from_scoring=True,
        template_created_at_utc="2000-01-01T00:00:00+00:00",
    )
    second = init_decision_log(
        artifacts_root=tmp_path / "b",
        data_version="dv_1",
        scoring_run="scr_1",
        user="pilot_pack",
        template_from_scoring=True,
        template_created_at_utc="2000-01-01T00:00:00+00:00",
    )

    assert Path(first["csv"]).read_text(encoding="utf-8") == Path(second["csv"]).read_text(encoding="utf-8")
    assert Path(first["jsonl"]).read_text(encoding="utf-8") == Path(second["jsonl"]).read_text(encoding="utf-8")
    assert _sha256(Path(first["xlsx"])) == _sha256(Path(second["xlsx"]))

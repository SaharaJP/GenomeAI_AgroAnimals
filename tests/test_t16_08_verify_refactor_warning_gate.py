from __future__ import annotations

import warnings
from pathlib import Path

from genomeai.refactor_verify import update_golden, verify_refactor


def test_t16_08_verify_refactor_standard_is_runtime_warning_free(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    golden_root = tmp_path / "golden"

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        update_res = update_golden(project_root=repo_root, golden_root=golden_root, scenario_names=["standard"])
        verify_res = verify_refactor(
            project_root=repo_root,
            golden_root=golden_root,
            scenario_names=["standard"],
            report_root=tmp_path / "reports",
        )

    assert update_res["ok"] is True
    assert verify_res["ok"] is True
    assert verify_res["scenarios"][0]["scenario"] == "standard"
    assert verify_res["scenarios"][0]["differences"] == 0

from __future__ import annotations

"""QC Rules Engine v2 (Target).

Legacy facade kept for backward compatibility. Implementation lives in core.application.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from core.application import load_qc_rules, new_qc_run_id, register_qc_run_outputs, run_qc_rules


def run_qc_v2(
    *,
    artifacts_root: Path,
    data_version: str,
    rules_path: Path,
    qc_run: Optional[str] = None,
    tenant_id: str = "default",
    max_issue_rows_per_rule: int = 200,
) -> Dict[str, Any]:
    artifacts_root = artifacts_root.resolve()
    actual_qc_run = qc_run or new_qc_run_id()
    out_dir = artifacts_root / data_version / "qc2" / actual_qc_run
    result = run_qc_rules(
        artifacts_root=artifacts_root,
        data_version=data_version,
        rules_path=rules_path,
        out_dir=out_dir,
        qc_run=actual_qc_run,
        tenant_id=tenant_id,
        max_issue_rows_per_rule=max_issue_rows_per_rule,
        manifest_type="qc2",
    )
    summary_path = Path(result["outputs"]["qc_summary_json"])
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    registration = register_qc_run_outputs(
        artifacts_root=artifacts_root,
        data_version=data_version,
        qc_run=actual_qc_run,
        out_dir=out_dir,
        summary=summary,
        kind="qc2",
    )
    result["outputs"] = {**dict(result.get("outputs") or {}), **registration}
    return result

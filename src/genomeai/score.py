from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.application.ml_pipeline import ScoringSummary, run_scoring as _run_scoring
from core.infra.compat import warn_legacy_import

warn_legacy_import(legacy_path="genomeai.score", new_path="core.application.ml_pipeline")


def run_scoring(
    *,
    artifacts_root: Path,
    data_version: str,
    model_version: str,
    scoring_run: Optional[str] = None,
    min_group_size: int | None = None,
    config_path: str | Path | None = None,
) -> Dict[str, Any]:
    return _run_scoring(
        artifacts_root=artifacts_root,
        data_version=data_version,
        model_version=model_version,
        scoring_run=scoring_run,
        min_group_size=min_group_size,
        config_path=config_path,
    )


__all__ = ["ScoringSummary", "run_scoring"]

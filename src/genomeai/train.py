from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.application.ml_pipeline import TrainSummary, train_productivity_model as _train_productivity_model
from core.infra.compat import warn_legacy_import

warn_legacy_import(legacy_path="genomeai.train", new_path="core.application.ml_pipeline")


def train_productivity_model(
    *,
    artifacts_root: Path,
    data_version: str,
    qc_run: str,
    model_version: Optional[str] = None,
    config_path: str | Path | None = None,
) -> Dict[str, Any]:
    return _train_productivity_model(
        artifacts_root=artifacts_root,
        data_version=data_version,
        qc_run=qc_run,
        model_version=model_version,
        config_path=config_path,
    )


__all__ = ["TrainSummary", "train_productivity_model"]

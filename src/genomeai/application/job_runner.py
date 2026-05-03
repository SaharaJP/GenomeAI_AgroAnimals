from __future__ import annotations

from core.application import job_runner as _target_module
from core.infra.compat import warn_legacy_import

warn_legacy_import(legacy_path="genomeai.application.job_runner", new_path="core.application.job_runner")

globals().update({name: getattr(_target_module, name) for name in dir(_target_module) if not name.startswith("__")})

__all__ = getattr(_target_module, "__all__", [])

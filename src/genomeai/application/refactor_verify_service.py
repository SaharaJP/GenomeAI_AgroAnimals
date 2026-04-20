from __future__ import annotations

import sys

from core.infra.compat import warn_legacy_import
from core.infra import refactor_verify_service as _target_module

warn_legacy_import(
    legacy_path="genomeai.application.refactor_verify_service",
    new_path="core.infra.refactor_verify_service",
)
sys.modules[__name__] = _target_module

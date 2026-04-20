from __future__ import annotations

import sys

from core.infra.compat import warn_legacy_import
from core.application import refactor_verify_runtime as _target_module

warn_legacy_import(legacy_path="genomeai.application.refactor_verify_runtime", new_path="core.application.refactor_verify_runtime")
sys.modules[__name__] = _target_module

from __future__ import annotations

import sys

from core.infra.compat import warn_legacy_import
from core.application import refactor_verify_dispatch as _target_module

warn_legacy_import(legacy_path="genomeai.application.refactor_verify_dispatch", new_path="core.application.refactor_verify_dispatch")
sys.modules[__name__] = _target_module

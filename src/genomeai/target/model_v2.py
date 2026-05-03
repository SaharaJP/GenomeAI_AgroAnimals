from __future__ import annotations

import sys

from core.infra.compat import warn_legacy_import
from core.domain import target_models as _target_module

warn_legacy_import(legacy_path="genomeai.target.model_v2", new_path="core.domain.target_models")
sys.modules[__name__] = _target_module

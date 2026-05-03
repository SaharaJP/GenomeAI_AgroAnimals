from __future__ import annotations

from core.infra.compat import warn_legacy_import
from core.security.matrix import *  # noqa: F401,F403

warn_legacy_import(legacy_path="web_cabinet.security_matrix", new_path="core.security.matrix")

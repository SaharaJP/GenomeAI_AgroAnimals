from __future__ import annotations

from core.infra.compat import warn_legacy_import
from core.observability import *  # noqa: F401,F403

warn_legacy_import(legacy_path="web_cabinet.observability", new_path="core.observability")

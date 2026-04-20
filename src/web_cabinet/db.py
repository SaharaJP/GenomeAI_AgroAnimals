from __future__ import annotations

from core.infra.compat import warn_legacy_import

warn_legacy_import(legacy_path="web_cabinet.db", new_path="core.infra.web_db")

from core.infra.web_db import *  # noqa: F401,F403

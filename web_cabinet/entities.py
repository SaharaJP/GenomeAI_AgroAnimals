from __future__ import annotations

from core.infra.compat import warn_legacy_import

warn_legacy_import(legacy_path='web_cabinet.entities', new_path='core.workflow.entities')

from core.workflow.entities import *  # noqa: F401,F403

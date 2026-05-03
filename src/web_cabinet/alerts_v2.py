from __future__ import annotations

from core.infra.compat import warn_legacy_import

warn_legacy_import(legacy_path='web_cabinet.alerts_v2', new_path='core.workflow.alerts')

from core.workflow.alerts import *  # noqa: F401,F403

from __future__ import annotations

from core.infra.compat import warn_legacy_import

warn_legacy_import(legacy_path='web_cabinet.decision_log_v2', new_path='core.workflow.decisions')

from core.workflow.decisions import *  # noqa: F401,F403

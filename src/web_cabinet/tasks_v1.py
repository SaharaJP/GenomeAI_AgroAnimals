from __future__ import annotations

from core.infra.compat import warn_legacy_import

warn_legacy_import(legacy_path='web_cabinet.tasks_v1', new_path='core.workflow.tasks')

from core.workflow.tasks import *  # noqa: F401,F403

from __future__ import annotations

from core.infra.compat import warn_legacy_import
from core.audit.events import *  # noqa: F401,F403
from core.audit.events import AUDIT_SCHEMA_VERSION, _canonical_action_group, _object_ref

warn_legacy_import(legacy_path="web_cabinet.audit", new_path="core.audit.events")

"""Workflow v2 helpers (domain, SLA, metrics).

This module is part of offline-core and can be used by both web-cabinet (API)
and web UI shells (Streamlit) without duplicating business logic.
"""

from .metrics import compute_tasks_metrics

__all__ = ["compute_tasks_metrics"]

"""Ensure src/ is on sys.path so analytics_v1 (which imports core) can be loaded."""
from __future__ import annotations

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[3]  # wt-bridge root
_src = _repo_root / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

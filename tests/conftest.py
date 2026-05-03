from __future__ import annotations

import sys
from pathlib import Path


def pytest_configure():
    """Ensure local packages are importable without editable install."""

    root = Path(__file__).resolve().parents[1]
    src = root / "src"

    # Ensure worktree root is at position 0 so web_cabinet.ai is found here
    # before any stale sys.modules entry from the main-repo editable install.
    if str(root) in sys.path:
        sys.path.remove(str(root))
    sys.path.insert(0, str(root))

    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))

    # Evict any cached web_cabinet that was loaded from a location without ai/
    for key in list(sys.modules.keys()):
        if key == "web_cabinet" or key.startswith("web_cabinet."):
            del sys.modules[key]

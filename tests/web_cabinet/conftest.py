"""
Ensures the worktree root is first in sys.path so that the worktree's
web_cabinet package (with ai/ and ai/context_helpers/) is found before
the main-repo's src/web_cabinet (which lacks the ai subpackage).
"""
import sys
from pathlib import Path

_wt_root = Path(__file__).resolve().parents[2]
if str(_wt_root) not in sys.path:
    sys.path.insert(0, str(_wt_root))
else:
    # Make sure worktree is at position 0, before /opt/genomeai/repo/src
    sys.path.remove(str(_wt_root))
    sys.path.insert(0, str(_wt_root))

# If web_cabinet was already cached from the main-repo src, evict it so
# the worktree version (with ai/) is loaded instead.
for _key in list(sys.modules.keys()):
    if _key == "web_cabinet" or _key.startswith("web_cabinet."):
        del sys.modules[_key]

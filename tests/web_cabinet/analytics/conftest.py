"""Ensure repo root is first on sys.path so web_cabinet.analytics is found."""
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
else:
    sys.path.remove(str(_repo_root))
    sys.path.insert(0, str(_repo_root))

# Evict any cached web_cabinet from src/ so the repo-root version (with analytics/) loads.
for _key in list(sys.modules.keys()):
    if _key == "web_cabinet" or _key.startswith("web_cabinet."):
        del sys.modules[_key]

"""Bootstrap package for src-layout.

Why this exists:
- The repository uses a `src/` layout (`src/genomeai/...`).
- Some entrypoints (e.g. installer launcher smoke) run `python -m genomeai.app_launcher`
  without editable install and without PYTHONPATH.

This shim makes `import genomeai.*` work from repository root by:
1) adding `./src` to `sys.path`
2) extending `genomeai.__path__` to include both `./genomeai` and `./src/genomeai`

It keeps backward compatibility for code that reads `genomeai.__version__`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from pkgutil import extend_path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if SRC.exists() and str(SRC) not in sys.path:
    # Make src-layout importable for subprocesses/entrypoints.
    sys.path.insert(0, str(SRC))

# Treat as namespace package that can find submodules in src/genomeai
__path__ = extend_path(__path__, __name__)  # type: ignore[name-defined]

__all__ = ["cli", "versioning", "validation", "contracts"]
__version__ = "0.0.1"

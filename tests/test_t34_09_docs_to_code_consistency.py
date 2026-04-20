from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_t34_09_docs_to_code_consistency_script_passes() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run([sys.executable, str(repo_root / 'scripts' / 'check_docs_to_code_consistency.py')], cwd=repo_root, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'docs_to_code_consistency=ok' in proc.stdout

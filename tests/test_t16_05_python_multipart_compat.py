from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_python(code: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    extra_path = str(ROOT / "src")
    env["PYTHONPATH"] = extra_path if not env.get("PYTHONPATH") else extra_path + os.pathsep + env["PYTHONPATH"]
    return subprocess.run(
        [sys.executable, "-W", "error::PendingDeprecationWarning", "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_t16_05_multipart_shim_supports_legacy_import_surface_without_warning() -> None:
    result = _run_python(
        "import multipart; "
        "from multipart.multipart import parse_options_header; "
        "assert hasattr(multipart, 'MultipartParser'); "
        "assert hasattr(multipart, 'QuerystringParser'); "
        "assert callable(parse_options_header); "
        "print('OK')"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "OK"


def test_t16_05_web_app_import_is_clean_under_pending_deprecation_error() -> None:
    result = _run_python("import web_cabinet.app; print('WEB_OK')")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("WEB_OK")

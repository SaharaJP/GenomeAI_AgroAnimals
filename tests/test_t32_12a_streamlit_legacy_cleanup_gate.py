from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_t32_12a_cleanup_gate_artifacts_exist() -> None:
    assert (ROOT / 'docs' / 'streamlit_legacy_cleanup_gate.md').exists()
    assert (ROOT / 'configs' / 'post_removal' / 'streamlit_legacy_cleanup_manifest_v1.json').exists()
    assert (ROOT / 'scripts' / 'validate_t32_12a_streamlit_legacy_cleanup.py').exists()
    assert (ROOT / 'scripts' / 'smoke_t32_12a_streamlit_legacy_cleanup.sh').exists()


def test_t32_12a_validator_passes() -> None:
    result = subprocess.run([sys.executable, 'scripts/validate_t32_12a_streamlit_legacy_cleanup.py'], cwd=ROOT, capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout.strip())
    report = json.loads((ROOT / 'configs' / 'post_removal' / 'streamlit_legacy_cleanup_report_v1.json').read_text(encoding='utf-8'))
    assert payload['status'] == 'pass'
    assert report['streamlit_contour_fully_removed'] is True
    assert report['checks']['operational_refs_clean'] is True
    assert report['checks']['runtime_imports_clean'] is True
    assert report['checks']['dependency_files_clean'] is True


def test_t32_12a_required_absence_paths() -> None:
    assert not (ROOT / 'streamlit_app').exists()
    assert not (ROOT / '.streamlit').exists()
    assert not (ROOT / 'scripts' / 'run_streamlit.sh').exists()


def test_t32_12a_manifest_tracks_historical_allowlist() -> None:
    manifest = json.loads((ROOT / 'configs' / 'post_removal' / 'streamlit_legacy_cleanup_manifest_v1.json').read_text(encoding='utf-8'))
    allowlist = manifest['allowed_historical_globs']
    assert 'docs/iterations/**' in allowlist
    assert 'installers/releases/**' in allowlist
    assert 'configs/post_removal/**' in allowlist

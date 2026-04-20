from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_t32_12_artifacts_exist() -> None:
    assert (ROOT / 'docs/streamlit_removal_and_cleanup.md').exists()
    assert (ROOT / 'configs/post_removal/streamlit_removal_regression_report_v1.json').exists()
    assert (ROOT / 'scripts/validate_t32_12_streamlit_removal.py').exists()
    assert (ROOT / 'scripts/smoke_t32_12_streamlit_removal.sh').exists()


def test_t32_12_streamlit_dirs_removed() -> None:
    assert not (ROOT / 'streamlit_app').exists()
    assert not (ROOT / '.streamlit').exists()


def test_t32_12_runtime_no_streamlit_dependency() -> None:
    for rel in ['pyproject.toml', 'deploy/docker-compose.yml', 'src/genomeai/app_launcher.py']:
        text = (ROOT / rel).read_text(encoding='utf-8').lower()
        assert 'streamlit' not in text


def test_t32_12_validator_matches_report() -> None:
    result = subprocess.run([sys.executable, 'scripts/validate_t32_12_streamlit_removal.py'], cwd=ROOT, capture_output=True, text=True, check=True)
    payload = json.loads(result.stdout)
    report = json.loads((ROOT / 'configs/post_removal/streamlit_removal_regression_report_v1.json').read_text(encoding='utf-8'))
    assert payload['status'] == report['status']
    assert payload['streamlit_present'] is False
    assert payload['streamlit_dependency_in_product'] is False
    assert payload['streamlit_dependency_in_deployment'] is False

from __future__ import annotations

import json
from pathlib import Path

from web_cabinet import smoke as smoke_module


def test_t17_05_web_smoke_main_writes_timing_json(monkeypatch, tmp_path: Path) -> None:
    payload = {
        'ok': True,
        'workdir': str(tmp_path / 'workdir'),
        'data_version': 'dv_test',
        'qc_run': 'qc_test',
        'model_version': 'model_test',
        'scoring_run': 'score_test',
        'report_version': 'report_test',
        'pack_zip': str(tmp_path / 'pack.zip'),
        'timings': {'rbac': 0.1, 'ingest_all': 0.2},
        'duration_sec': 1.23,
    }
    monkeypatch.setattr(smoke_module, 'run_web_smoke_scenario', lambda **kwargs: payload)
    out_json = tmp_path / 'timings.json'

    exit_code = smoke_module.main(['--workdir', str(tmp_path / 'manual'), '--timing-json', str(out_json)])

    assert exit_code == 0
    saved = json.loads(out_json.read_text(encoding='utf-8'))
    assert saved['duration_sec'] == 1.23
    assert saved['timings']['rbac'] == 0.1

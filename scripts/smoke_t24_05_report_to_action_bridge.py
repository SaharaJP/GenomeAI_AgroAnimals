from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
for p in (ROOT, SRC):
    ps = str(p)
    if ps not in sys.path:
        sys.path.insert(0, ps)

from core.report_to_action_bridge import build_report_bridge_snapshot


if __name__ == '__main__':
    snapshot = build_report_bridge_snapshot(
        report_ref={
            'data_version': 'dv_smoke',
            'qc_run': 'qc_smoke',
            'model_version': 'mdl_smoke',
            'scoring_run': 'score_smoke',
            'report_version': 'report_smoke',
        },
        toc=[{'level': 1, 'title': 'QC', 'anchor': 'qc'}],
        fact_pack={'top_lists': {'priority': [{'animal_id': 'A-1', 'action': 'PRIORITY', 'confidence': 'HIGH'}]}},
    )
    assert snapshot['summary']['row_contexts_n'] == 1
    assert snapshot['summary']['section_contexts_n'] == 1
    print('OK: report-to-action bridge smoke passed')

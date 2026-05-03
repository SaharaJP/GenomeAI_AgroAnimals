from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
import tempfile

import pandas as pd

from core.economics import (
    build_operational_what_if_snapshot,
    create_operational_what_if_followup_worklist_use_case,
    record_operational_what_if_decision_use_case,
)
from core.infra.web_db import init_db


def _seed(tmp: Path) -> Path:
    input_dir = tmp / 'input'
    input_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {'animal_id':'A1001','farm_id':'F1','status':'active','breed':'Holstein','current_pen_id':'P1','current_pen_name':'Fresh pen'},
        {'animal_id':'A1002','farm_id':'F1','status':'active','breed':'Holstein','current_pen_id':'P2','current_pen_name':'Hospital pen'},
    ]).to_csv(input_dir/'dm_animals.csv', index=False)
    pd.DataFrame([
        {'animal_id':'A1001','lactation_id':'L1','parity':2,'calving_date':'2026-03-20','scc_cells_ml':180000},
        {'animal_id':'A1002','lactation_id':'L2','parity':3,'calving_date':'2026-02-10','scc_cells_ml':330000},
    ]).to_csv(input_dir/'dm_lactations.csv', index=False)
    pd.DataFrame([
        {'animal_id':'A1001','date':'2026-04-03','milk_kg':31.0,'scc_cells_ml':180000},
        {'animal_id':'A1002','date':'2026-04-03','milk_kg':20.0,'scc_cells_ml':330000},
    ]).to_csv(input_dir/'dm_milkings_daily.csv', index=False)
    pd.DataFrame([
        {'animal_id':'A1002','event_id':'HE1','event_date':'2026-04-01','event_type':'mastitis','severity':'high'},
    ]).to_csv(input_dir/'dm_health_events.csv', index=False)
    pd.DataFrame([
        {'animal_id':'A1002','treatment_id':'T1','start_date':'2026-04-02','end_date':'2026-04-06'},
    ]).to_csv(input_dir/'dm_treatments.csv', index=False)
    pd.DataFrame([
        {'animal_id':'A1001','event_date':'2026-04-03','event_type':'heat_observed','result':'candidate'},
    ]).to_csv(input_dir/'dm_repro_events.csv', index=False)
    return input_dir


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        input_dir = _seed(root)
        snap = build_operational_what_if_snapshot(input_dir=input_dir, asof_date=date(2026,4,3), object_type='animal', object_id='A1002', scenario_family='cull_keep', project_root=Path.cwd(), data_version='dv_smoke')
        assert snap['schema'] == 'genomeai.operational_what_if.v1'
        assert snap['scenario_rows']
        conn = sqlite3.connect(root / 'web.db')
        conn.row_factory = sqlite3.Row
        init_db(conn)
        dec = record_operational_what_if_decision_use_case(conn=conn, tenant_id='default', user_id=1, username='hm', role='HerdManager', snapshot=snap, scenario_key=snap['recommended_scenario_key'], reason='smoke', comment='ok', request_id='req-smoke')
        assert dec['decision_id']
        wl = create_operational_what_if_followup_worklist_use_case(conn=conn, tenant_id='default', user_id=1, username='hm', role='HerdManager', snapshot=snap, scenario_key=snap['recommended_scenario_key'], request_id='req-smoke-wl')
        assert wl['worklist_id']
    print('OK: operational what-if smoke passed')


if __name__ == '__main__':
    main()

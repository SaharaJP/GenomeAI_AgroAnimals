from __future__ import annotations

import sqlite3
import tempfile
from datetime import date
from pathlib import Path

from core.economics import build_cow_value_snapshot, create_culling_review_worklist_use_case, record_cow_value_decision_use_case
from core.infra.web_db import init_db


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        input_dir = base / 'input'
        _write(input_dir / 'dm_animals.csv', 'tenant_id,animal_id,farm_id,site_id,current_pen_id,current_pen_name,status,breed,sex,birth_date\ndefault,A1001,F1,S1,P1,Fresh,active,Holstein,F,2022-01-01\n')
        _write(input_dir / 'dm_lactations.csv', 'tenant_id,animal_id,lactation_id,parity,calving_date,scc_cells_ml\ndefault,A1001,L1,5,2025-11-01,320000\n')
        _write(input_dir / 'dm_milkings_daily.csv', 'tenant_id,animal_id,date,milk_kg\ndefault,A1001,2026-04-01,21\ndefault,A1001,2026-04-02,22\ndefault,A1001,2026-04-03,20\n')
        _write(input_dir / 'dm_health_events.csv', 'tenant_id,event_id,animal_id,event_date,event_type,severity\ndefault,HE1,A1001,2026-03-20,mastitis,high\n')
        _write(input_dir / 'dm_treatments.csv', 'tenant_id,treatment_id,animal_id,start_date,end_date,treatment_type\ndefault,TR1,A1001,2026-03-20,2026-04-10,antibiotic\n')
        _write(input_dir / 'dm_repro_events.csv', 'tenant_id,repro_event_id,animal_id,event_date,event_type,result\ndefault,RE1,A1001,2026-03-01,preg_check,open\n')
        snap = build_cow_value_snapshot(input_dir=input_dir, asof_date=date(2026, 4, 3), animal_id='A1001', project_root=Path.cwd(), data_version='dv_t27_01')
        assert snap['recommended_action'] in {'keep', 'breed', 'treat', 'cull', 'defer'}
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        init_db(conn)
        dec = record_cow_value_decision_use_case(conn=conn, tenant_id='default', user_id=1, username='user', role='Zootech', snapshot=snap, action=str(snap['recommended_action']), reason='smoke', comment='ok', request_id='smoke-decision')
        wl = create_culling_review_worklist_use_case(conn=conn, tenant_id='default', user_id=1, username='user', role='Zootech', snapshot=snap, request_id='smoke-worklist')
        assert dec['decision_id'] and wl['worklist_id']
    print('OK: cow value / culling engine smoke passed')


if __name__ == '__main__':
    main()

from __future__ import annotations

import sqlite3
import tempfile
from datetime import date
from pathlib import Path

from core.economics import build_milk_quality_scc_snapshot, create_milk_quality_followup_worklist_use_case
from core.infra.web_db import init_db


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        input_dir = base / 'input'
        _write(input_dir / 'dm_animals.csv', 'tenant_id,animal_id,farm_id,site_id,current_pen_id,current_pen_name,status,breed,sex,birth_date\ndefault,A1001,F1,S1,P1,Fresh,active,Holstein,F,2022-01-01\ndefault,A1002,F1,S1,P2,Hospital,active,Holstein,F,2021-01-01\n')
        _write(input_dir / 'dm_milkings_daily.csv', 'tenant_id,animal_id,date,milk_kg,scc_cells_ml\ndefault,A1001,2026-04-03,31,120000\ndefault,A1002,2026-04-03,23,420000\n')
        _write(input_dir / 'dm_health_events.csv', 'tenant_id,event_id,animal_id,event_date,event_type,severity\ndefault,HE1,A1002,2026-03-20,mastitis,high\n')
        _write(input_dir / 'dm_treatments.csv', 'tenant_id,treatment_id,animal_id,start_date,end_date,treatment_type\ndefault,TR1,A1002,2026-03-21,2026-04-10,antibiotic\n')
        snap = build_milk_quality_scc_snapshot(input_dir=input_dir, asof_date=date(2026, 4, 3), project_root=Path.cwd(), data_version='dv_t27_02')
        assert snap['bulk_tank']['estimated_bulk_tank_scc'] is not None
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        init_db(conn)
        res = create_milk_quality_followup_worklist_use_case(
            conn=conn,
            tenant_id='default',
            user_id=1,
            username='user',
            role='Vet',
            snapshot=snap,
            target_level='animal',
            target_id='A1002',
            request_id='smoke-milk-quality',
        )
        assert res['worklist_id']
    print('OK: milk quality / SCC cockpit smoke passed')


if __name__ == '__main__':
    main()

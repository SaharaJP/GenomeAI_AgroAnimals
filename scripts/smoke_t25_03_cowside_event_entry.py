from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

from core.infra.web_db import init_db
from core.operational import create_cowside_event_entry_use_case, search_cowside_animals


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / 'artifacts' / 'dv_smoke' / 'canonical'
        root.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([
            {'animal_id': 'A-1', 'status': 'active', 'breed': 'Holstein', 'sex': 'F', 'farm_id': 'farm-1', 'site_id': 'site-1', 'current_pen_id': 'P-1', 'current_pen_name': 'Fresh cows'},
        ]).to_csv(root / 'dm_animals.csv', index=False)
        pd.DataFrame([
            {'animal_id': 'A-1', 'lactation_id': 'L1', 'parity': 2, 'calving_date': '2026-03-01', 'scc_cells_ml': 150000},
        ]).to_csv(root / 'dm_lactations.csv', index=False)

        rows = search_cowside_animals(input_dir=root, asof_date=pd.Timestamp('2026-04-02').date(), role='Vet', q='A-1', limit=5)
        assert rows and rows[0]['animal_id'] == 'A-1'

        conn = sqlite3.connect(':memory:', check_same_thread=False)
        conn.row_factory = sqlite3.Row
        init_db(conn)
        res = create_cowside_event_entry_use_case(
            conn=conn,
            tenant_id='default',
            animal_id='A-1',
            template_key='treatment_started',
            event_ts='2026-04-02T08:15:00+00:00',
            user_id=1,
            username='vet',
            role='Vet',
            comment='smoke protocol',
            create_follow_up=True,
            follow_up_due_at='2026-04-03',
            data_version='dv_smoke',
            request_id='rq-smoke',
        )
        assert res['event_id']
        assert res['worklist_id']
        conn.close()
    print('OK: cowside event entry smoke passed')


if __name__ == '__main__':
    main()

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd

from core.economics import build_fresh_cows_transition_snapshot


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        pd.DataFrame([
            {'animal_id':'A1001','farm_id':'F1','status':'active','breed':'Holstein'},
            {'animal_id':'A1002','farm_id':'F1','status':'active','breed':'Holstein'},
        ]).to_csv(base/'dm_animals.csv', index=False)
        pd.DataFrame([
            {'animal_id':'A1001','lactation_id':'L1','parity':2,'calving_date':'2026-03-20','scc_cells_ml':180000},
            {'animal_id':'A1002','lactation_id':'L2','parity':3,'calving_date':'2026-03-10','scc_cells_ml':350000},
        ]).to_csv(base/'dm_lactations.csv', index=False)
        pd.DataFrame([
            {'animal_id':'A1001','date':'2026-04-03','milk_kg':31.0,'scc_cells_ml':180000},
            {'animal_id':'A1002','date':'2026-04-03','milk_kg':22.0,'scc_cells_ml':350000},
        ]).to_csv(base/'dm_milkings_daily.csv', index=False)
        pd.DataFrame([
            {'animal_id':'A1002','event_id':'HE1','event_date':'2026-03-28','event_type':'metritis','severity':'high'},
        ]).to_csv(base/'dm_health_events.csv', index=False)
        pd.DataFrame([
            {'animal_id':'A1002','treatment_id':'T1','start_date':'2026-03-29','end_date':'2026-04-05'},
        ]).to_csv(base/'dm_treatments.csv', index=False)
        pd.DataFrame(columns=['animal_id','repro_event_id','event_date','event_type','result']).to_csv(base/'dm_repro_events.csv', index=False)
        pd.DataFrame(columns=['animal_id','test_date','scc_cells_ml']).to_csv(base/'dm_testday.csv', index=False)
        snap = build_fresh_cows_transition_snapshot(input_dir=base, asof_date=date(2026,4,3), project_root=Path(__file__).resolve().parents[1], data_version='dv_t27_04')
        assert int((snap.get('summary_metrics') or {}).get('fresh_cows_n') or 0) == 2
        assert list(snap.get('animal_rows') or [])
    print('OK: fresh cows / transition economics smoke passed')


if __name__ == '__main__':
    main()

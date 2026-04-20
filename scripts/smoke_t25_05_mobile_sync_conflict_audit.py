from __future__ import annotations

import sqlite3
from pathlib import Path

from core.infra.web_db import init_db
from core.mobile_sync import build_mobile_action_key, execute_mobile_sync_action, get_mobile_sync_action

ROOT = Path(__file__).resolve().parents[1]


conn = sqlite3.connect(':memory:', check_same_thread=False)
conn.row_factory = sqlite3.Row
init_db(conn)

payload = {'animal_id': 'A-100', 'data_version': 'dv_t25_05'}
key = build_mobile_action_key(page_key='cowside_event_entry', action_kind='animal_event.cowside_entry', object_type='animal', object_id='A-100', nonce='smoke')

res = execute_mobile_sync_action(
    conn,
    tenant_id='default',
    user_id=1,
    username='smoke',
    role='Vet',
    page_key='cowside_event_entry',
    action_kind='animal_event.cowside_entry',
    action_key=key,
    object_type='animal',
    object_id='A-100',
    payload=payload,
    request_id='rq-smoke',
    executor=lambda _conn, data: {'event_id': 'ev-smoke', 'data_version': data['data_version']},
)
assert res['state'] == 'saved'
row = get_mobile_sync_action(conn, tenant_id='default', action_key=key)
assert row['status'] == 'saved'
assert row['linked_event_id'] == 'ev-smoke'

print('OK: mobile sync / conflict / audit smoke passed')

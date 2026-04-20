from __future__ import annotations

import sqlite3

from core.infra.web_db import init_db
from core.workflow import append_worklist_comment_use_case, create_worklist_use_case, get_worklist


def main() -> None:
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    created = create_worklist_use_case(
        conn=conn,
        tenant_id='default',
        worklist_type='vet',
        title='Smoke vet round',
        priority=2,
        due_at='2026-04-02T08:00:00+00:00',
        assignee_team='team-health',
        confidence=0.82,
        object_type='animal',
        object_id='AN-SMOKE',
        linked_source_facts=[{'text': 'mastitis risk high'}],
        user_id=1,
        username='smoke',
        role='Vet',
        request_id='smoke-create',
    )
    wid = str(created['worklist_id'])
    append_worklist_comment_use_case(
        conn=conn,
        tenant_id='default',
        worklist_id=wid,
        user_id=1,
        username='smoke',
        role='Vet',
        comment='checked on mobile',
        source='mobile_worklists',
        request_id='smoke-comment',
    )
    row = get_worklist(conn, tenant_id='default', worklist_id=wid) or {}
    comments = [x for x in list(row.get('attachments') or []) if str(x.get('kind') or '') == 'comment']
    assert comments and comments[0]['comment'] == 'checked on mobile'
    print('OK: mobile worklists smoke passed')


if __name__ == '__main__':
    main()

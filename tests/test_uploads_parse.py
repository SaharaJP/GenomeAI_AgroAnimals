"""parse_file: CSV / XLSX → list[dict]."""
from __future__ import annotations

import io
import pytest


def test_parse_csv_milkings():
    from web_cabinet.uploads_v1 import parse_file, generate_template
    body, _, _ = generate_template('milkings', 'csv')
    rows = parse_file('milkings', body, 'milkings.csv')
    # Sample row from template should round-trip
    assert len(rows) == 1
    assert rows[0]['animal_id'] == '1234'
    assert str(rows[0]['milk_kg']) in ('28.5', '28.5')


def test_parse_xlsx_milkings():
    from web_cabinet.uploads_v1 import parse_file
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(['animal_id', 'date', 'milk_kg'])
    ws.append(['A1', '2026-05-01', 28.5])
    ws.append(['A2', '2026-05-01', 30.0])
    out = io.BytesIO()
    wb.save(out); wb.close()
    rows = parse_file('milkings', out.getvalue(), 'data.xlsx')
    assert len(rows) == 2
    assert rows[0]['animal_id'] == 'A1'


def test_parse_drops_empty_rows():
    from web_cabinet.uploads_v1 import parse_file
    csv_body = '﻿animal_id,date,milk_kg\nA1,2026-05-01,28.5\n,,\nA2,2026-05-02,29.0\n'.encode('utf-8')
    rows = parse_file('milkings', csv_body, 'd.csv')
    assert len(rows) == 2


def test_parse_unsupported_extension_raises():
    from web_cabinet.uploads_v1 import parse_file
    with pytest.raises(ValueError, match='unsupported_format'):
        parse_file('milkings', b'x', 'd.txt')


def test_parse_cp1251_fallback():
    """Russian content saved as Windows-1251 still parses (best-effort)."""
    from web_cabinet.uploads_v1 import parse_file
    text = 'animal_id,event_date,event_type,notes\nA1,2026-05-01,mastitis,Левая передняя\n'
    body = text.encode('cp1251')
    rows = parse_file('health_events', body, 'd.csv')
    assert rows[0]['notes'] == 'Левая передняя'
